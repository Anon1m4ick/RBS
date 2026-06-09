# Oblak Firecracker Stage

Этот документ описывает этап **3. Firecracker — выполнение кода** из проекта Oblak. Этап не реализует Server API, Code Verifier и CDK CLI. Он получает уже проверенный bundle функции и один event, запускает функцию внутри Firecracker microVM и пишет audit trail.

## Граница ответственности

Вход от предыдущих этапов:

- директория с кодом функции;
- entrypoint в формате `handler.py:handle`;
- JSON event;
- `function_id` и `request_id`;
- подготовленный rootfs с установленным Python и `oblak.firecracker.guest_runner`.

Выход для Server API:

- статус запуска: `SUCCESS`, `FUNCTION_ERROR`, `FAILED`, `TIMEOUT` или `DRY_RUN`;
- структурированный результат функции из serial console;
- директория запуска с manifest, tar payload, логами Firecracker и metrics;
- append-only audit log.

## Архитектура

Host-side код находится в `oblak/firecracker/`:

- `config.py` проверяет Linux/KVM, Firecracker binary, kernel и rootfs;
- `bundle.py` валидирует bundle, запрещает symlink/path traversal и собирает `code.tar`;
- `api.py` отправляет Firecracker REST API запросы через Unix socket;
- `executor.py` создает run directory, function drive, конфигурирует VM и ждет завершения;
- `audit.py` пишет JSONL audit log с hash-chain;
- `guest_runner.py` устанавливается внутрь rootfs и запускает пользовательский handler.

Схема выполнения:

1. Server API передает Firecracker-этапу verified bundle и event.
2. Host создает private run directory `0700`.
3. Bundle пакуется в `code.tar`; рядом пишутся `event.json` и `manifest.json`.
4. Из staging-директории создается ext4 image `function.ext4`.
5. Firecracker стартует с rootfs drive и read-only function drive.
6. Guest runner монтирует `/dev/vdb` как read-only, распаковывает код в `/tmp`, выставляет read-only права, применяет resource limits, переходит на `nobody` и вызывает handler.
7. Результат печатается в serial console между маркерами `OBLAK_RESULT_BEGIN` / `OBLAK_RESULT_END`.
8. Host парсит результат, пишет audit event и возвращает ответ вызывающему API.

По умолчанию network interface не подключается. Если конкретной функции нужен outbound network, host должен заранее создать TAP interface и явно запустить executor с `--enable-network --tap-dev ...`.

## Rootfs Contract

Firecracker сам по себе только стартует microVM. Чтобы внутри VM действительно выполнился Python handler, rootfs должен выполнить guest runner при загрузке.

Минимальный контракт rootfs:

- Linux rootfs с Python 3;
- файл `/opt/oblak/guest_runner.py`, соответствующий `oblak/firecracker/guest_runner.py`;
- systemd service `oblak-function.service`;
- в guest виден read-only function drive как `/dev/vdb`;
- serial console `ttyS0` выводится в stdout Firecracker process.

Пример systemd unit:

```ini
[Unit]
Description=Oblak function runner
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/oblak/guest_runner.py --device /dev/vdb
StandardOutput=tty
StandardError=tty
TTYPath=/dev/ttyS0

[Install]
WantedBy=multi-user.target
```

Kernel boot args по умолчанию:

```text
console=ttyS0 reboot=k panic=1 pci=off random.trust_cpu=on quiet systemd.unit=oblak-function.service
```

## Security Requirements

Основные требования Firecracker-этапа:

- запускать пользовательский код только внутри microVM;
- не монтировать host directories внутрь VM;
- передавать код через read-only block device;
- не подключать сеть по умолчанию;
- ограничивать CPU, memory, file size, number of open files и processes внутри guest;
- запускать handler не от root, а от `nobody`;
- завершать VM по timeout;
- писать audit events для подготовки, старта, timeout и завершения;
- сохранять hash bundle в manifest и audit log;
- запрещать symlinks, absolute paths и `..` в bundle/tar.

## STRIDE

| Категория | Угроза | Mitigation в этом этапе |
| --- | --- | --- |
| Spoofing | Подмена `function_id` или `request_id` между API и executor | Эти значения пишутся в manifest и audit log; production API должен подписывать job envelope или передавать его через доверенный internal channel |
| Tampering | Path traversal в bundle, symlink на host файл, изменение payload после проверки | `bundle.py` запрещает symlink и выход из bundle root; payload хешируется; function drive монтируется read-only |
| Repudiation | Пользователь отрицает запуск или результат | `audit.py` пишет append-only JSONL события с hash-chain |
| Information Disclosure | Пользовательский код читает host secrets или чужие данные | Код находится в microVM без host mounts; rootfs и function drive read-only; handler запускается как `nobody`; сеть выключена по умолчанию |
| Denial of Service | Бесконечный цикл, fork bomb, гигантский вывод, расход RAM | Host timeout, `vcpu_count`, `mem_size_mib`, guest `RLIMIT_CPU`, `RLIMIT_AS`, `RLIMIT_NPROC`, `RLIMIT_NOFILE`, `RLIMIT_FSIZE` |
| Elevation of Privilege | Escape из Python process или container runtime | Главная граница изоляции — KVM microVM; внутри guest дополнительно drop privileges; production должен запускать VMM через Firecracker jailer |

## Запуск в dry-run режиме

Dry-run работает на macOS/Linux без KVM. Он проверяет bundle, создает staging payload и audit log, но не стартует VM:

```bash
python3 -m oblak.firecracker.cli \
  --bundle examples/hello \
  --event-file examples/hello/event.json \
  --function-id hello \
  --dry-run
```

## Реальный запуск на Linux/KVM

Предварительные требования:

- Linux x86_64/aarch64 с `/dev/kvm`;
- read/write доступ текущего пользователя к `/dev/kvm`;
- Firecracker binary;
- uncompressed guest kernel image;
- ext4 rootfs image с установленным guest runner;
- `mkfs.ext4` на host для сборки function drive.

Команда:

```bash
python3 -m oblak.firecracker.cli \
  --bundle examples/hello \
  --event-file examples/hello/event.json \
  --function-id hello \
  --firecracker-bin /usr/local/bin/firecracker \
  --kernel /var/lib/oblak/firecracker/vmlinux \
  --rootfs /var/lib/oblak/firecracker/rootfs.ext4 \
  --timeout 10 \
  --memory-mib 128
```

## Тестовые malicious scenarios

`examples/malicious_file_read` пытается прочитать `/etc/shadow`. Ожидаемое поведение: host files недоступны вообще, а guest `/etc/shadow` не должен читаться процессом `nobody`.

`examples/malicious_network` пытается открыть TCP-соединение. Ожидаемое поведение: без `--enable-network` у VM нет сетевого интерфейса для outbound traffic.

## Open Items

Эти пункты обязательны для production, но вынесены за рамки минимального этапа:

- запуск Firecracker через `jailer` с отдельным uid/gid, chroot и cgroups;
- сборка минимального hardened rootfs и автоматическая установка guest runner;
- seccomp policy для VMM и host-side helper processes;
- vsock channel вместо serial console для результата;
- snapshot/restore для ускорения cold start;
- централизованная отправка audit logs вне host;
- строгий allowlist системных вызовов и capabilities внутри guest;
- quota на размер run directory и log rotation.

## Связь с остальными этапами

Code Verifier должен до этого этапа отклонять явно вредоносные bundle, но Firecracker-этап не доверяет этому результату полностью. Поэтому здесь есть повторная защита от traversal/symlink, read-only packaging, guest privilege drop и resource limits.

Server API должен решать auth, authorization, URL invoke и хранение функций. Firecracker-этап принимает только внутреннюю задачу на запуск и возвращает результат.

