# Oblak Firecracker Runner

Этап **Firecracker — выполнение кода** для проекта Oblak.

Этот подпроект не реализует Server API, Code Verifier и CDK CLI. Он принимает уже проверенный bundle Python-функции, подготавливает payload, стартует Firecracker microVM и возвращает результат выполнения.

## Что внутри

- `oblak/firecracker/executor.py` — host-side orchestration Firecracker;
- `oblak/firecracker/guest_runner.py` — guest-side запуск `handler.py:handle` внутри VM;
- `oblak/firecracker/bundle.py` — безопасная подготовка bundle;
- `oblak/firecracker/audit.py` — audit log с hash-chain;
- `docs/firecracker-stage.md` — архитектура, STRIDE, security requirements и rootfs contract;
- `examples/` — benign и malicious примеры;
- `tests/` — unit-тесты без KVM.

## Установка для разработки

```bash
cd project/firecracker-runner
python3 -m pip install -e .
```

## Dry-run без KVM

```bash
cd project/firecracker-runner
python3 -m oblak.firecracker.cli \
  --bundle examples/hello \
  --event-file examples/hello/event.json \
  --function-id hello \
  --dry-run
```

Dry-run проверяет bundle, создает staging payload и audit log, но не стартует Firecracker.

## Реальный запуск

Для настоящего запуска нужен Linux host с `/dev/kvm`, Firecracker binary, kernel image, rootfs image и `mkfs.ext4`.

```bash
cd project/firecracker-runner
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

## Проверки

```bash
cd project/firecracker-runner
python3 -m unittest discover -s tests -v
python3 -m compileall oblak tests
```

