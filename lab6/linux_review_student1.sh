#!/bin/bash
###############################################################################
# linux_review_student1.sh  --  Lab 6: Secure Deployment Environment
# Student 1: small LinPEAS-style system review tool. Target: Debian 13 Trixie.
# Checks (section 4 of the lab document): OS, Kernel, Time, Packages, Logging.
# LOTL approach: uses only standard commands, reads files read-only, and only
# REPORTS insecure configuration - it never changes the system.
# Run as root for full coverage:  sudo ./linux_review_student1.sh
###############################################################################

OK=0; WARN=0; FAIL=0   # finding counters for the summary

# --- output helpers ---------------------------------------------------------
section() { echo; echo "=== $1 ==="; }
ok()   { echo "  [ OK ]  $1"; OK=$((OK+1));     }
warn() { echo "  [WARN]  $1"; WARN=$((WARN+1)); }
fail() { echo "  [FAIL]  $1"; FAIL=$((FAIL+1)); }
info() { echo "  [INFO]  $1"; }
have() { command -v "$1" >/dev/null 2>&1; }

# --- environment: is systemd booted? are we inside a container? -------------
[ -d /run/systemd/system ] && SYSTEMD=1 || SYSTEMD=0
[ -f /.dockerenv ]         && CONTAINER=1 || CONTAINER=0

# Is a service active? Try systemd first, fall back to the process list.
svc_active() {            # $1 = systemd unit, $2 = process name
    if [ "$SYSTEMD" = 1 ] && have systemctl; then
        systemctl is-active "$1" >/dev/null 2>&1 && return 0
    fi
    ps -e -o comm= 2>/dev/null | grep -qE "^$2" && return 0
    return 1
}

# 1. OPERATING SYSTEM --------------------------------------------------------
# Goal: an OS version out of support receives no security patches.
check_os() {
    section "1. OPERATING SYSTEM"
    local name ver major
    if [ -r /etc/os-release ]; then
        name=$(. /etc/os-release; echo "$NAME")
        ver=$(.  /etc/os-release; echo "$VERSION")
        major=$(. /etc/os-release; echo "$VERSION_ID" | grep -oE '[0-9]+' | head -1)
    elif [ -r /etc/debian_version ]; then
        name="Debian"; ver=$(cat /etc/debian_version)
        major=$(echo "$ver" | grep -oE '[0-9]+' | head -1)
    fi
    info "Distribution: $name $ver"
    case "$major" in
        13)         ok   "Debian 13 (Trixie) - current stable, supported until 2028." ;;
        12)         ok   "Debian 12 (Bookworm) - supported (full support ends 2026-06)." ;;
        11)         warn "Debian 11 (Bullseye) - LTS ends 2026-06; plan an upgrade." ;;
        6|7|8|9|10) fail "Debian $major - END OF LIFE: no more security updates." ;;
        *)          info "Verify the support status of this OS version manually." ;;
    esac
}

# 2. KERNEL ------------------------------------------------------------------
# Goal: old kernel = known CVEs; long uptime = kernel almost certainly unpatched.
check_kernel() {
    section "2. KERNEL"
    info "Kernel: $(uname -r) ($(uname -m))"
    [ "$CONTAINER" = 1 ] && info "Container - kernel/uptime belong to the host."
    local secs days
    secs=$(cut -d. -f1 /proc/uptime 2>/dev/null)
    days=$(( ${secs:-0} / 86400 ))
    if [ "$days" -gt 30 ]; then
        warn "Uptime is $days days - the kernel was very likely not patched (an update needs a reboot)."
    else
        ok "Uptime is $days days."
    fi
    info "Check this kernel version against the Debian security tracker for CVEs."
}

# 3. TIME MANAGEMENT ---------------------------------------------------------
# Goal: wrong time breaks log correlation, TLS validation and time-based auth.
check_time() {
    section "3. TIME MANAGEMENT"
    local tz=""
    [ "$SYSTEMD" = 1 ] && have timedatectl && \
        tz=$(timedatectl show -p Timezone --value 2>/dev/null)
    [ -z "$tz" ] && [ -r /etc/timezone ] && tz=$(cat /etc/timezone)
    info "Timezone: ${tz:-unknown}"
    case "$tz" in
        *UTC*) ok   "Timezone is UTC - no daylight-saving time jumps in logs." ;;
        *)     warn "Timezone '$tz' may use daylight-saving time; UTC is recommended for servers." ;;
    esac
    if svc_active systemd-timesyncd systemd-timesyn \
       || svc_active chrony chronyd || svc_active ntp ntpd; then
        ok "A time-synchronisation service (NTP) is active."
    elif [ "$CONTAINER" = 1 ]; then
        info "No NTP inside the container - expected; time is synced by the host."
    else
        fail "No NTP service is active - the system clock can drift."
    fi
}

# 4. PACKAGES INSTALLED ------------------------------------------------------
# Goal: fewer packages = smaller attack surface; no legacy cleartext services.
check_packages() {
    section "4. PACKAGES INSTALLED"
    if ! have dpkg; then info "dpkg not available - not a Debian system."; return; fi
    local pkgs gui legacy dev
    pkgs=$(dpkg -l 2>/dev/null | awk '/^ii/{print $2}' | sed 's/:.*//')
    info "Installed packages: $(echo "$pkgs" | grep -c .)"

    gui=$(echo "$pkgs"    | grep -E '^(xserver-xorg|xorg|x11-common|gnome|kde|gdm3|lightdm)')
    legacy=$(echo "$pkgs" | grep -E '^(telnet|telnetd|inetutils-telnet|rsh-client|rsh-server|nis|tftp|tftp-hpa|tftpd|finger)$')
    dev=$(echo "$pkgs"    | grep -E '^(gcc|g\+\+|make|build-essential)$')

    if [ -n "$gui" ]; then
        warn "Graphical-environment packages (not needed on a server): $(echo $gui | tr '\n' ' ')"
    else
        ok "No graphical environment installed."
    fi
    if [ -n "$legacy" ]; then
        fail "Legacy cleartext-protocol packages found: $(echo $legacy | tr '\n' ' ')"
    else
        ok "No legacy network packages (telnet, rsh, tftp...)."
    fi
    [ -n "$dev" ] && info "Compilers/build tools present (best removed on a hardened server): $(echo $dev | tr '\n' ' ')"
}

# 5. LOGGING -----------------------------------------------------------------
# Goal: logs must survive reboots and be hard for an intruder to erase.
check_logging() {
    section "5. LOGGING"
    if [ "$SYSTEMD" = 1 ]; then
        if svc_active systemd-journald systemd-journal; then
            ok "systemd-journald is active."
        else
            warn "systemd-journald is not active."
        fi
        if [ -d /var/log/journal ]; then
            ok "Journal is persistent (/var/log/journal) - logs survive reboots."
        else
            warn "Journal is volatile (no /var/log/journal) - logs are lost on reboot."
        fi
    else
        info "Not booted with systemd - skipping journald check (expected in a container)."
    fi

    if svc_active rsyslog rsyslogd; then
        ok "rsyslog daemon is running."
    else
        info "rsyslog daemon is not running."
    fi

    if [ -r /etc/rsyslog.conf ]; then
        local cfg mode
        cfg=$(cat /etc/rsyslog.conf /etc/rsyslog.d/*.conf 2>/dev/null | grep -vE '^[[:space:]]*#')
        if echo "$cfg" | grep -qE '[[:space:]]@@?[A-Za-z0-9.]'; then
            ok "Remote logging is configured (logs forwarded off-host)."
        else
            warn "No remote logging - an intruder could erase local logs. Forward them with @server / @@server."
        fi
        mode=$(echo "$cfg" | grep -iE 'FileCreateMode' | grep -oE '[0-7]{3,4}' | tail -1)
        if [ -n "$mode" ]; then
            case "$mode" in
                *0|*1) ok   "Log file mode $mode - other users cannot read logs." ;;
                *)     warn "Log file mode $mode is readable by other users; 0640 is recommended." ;;
            esac
        fi
    fi
}

# --- main -------------------------------------------------------------------
echo "Linux Security Review - Student 1 (OS / Kernel / Time / Packages / Logging)"
echo "Host: $(hostname)   Date: $(date '+%Y-%m-%d %H:%M')"
[ "$CONTAINER" = 1 ] && echo "Environment: running inside a container."
[ "$(id -u)" != 0 ]  && echo "Note: not running as root - some checks may be limited."

check_os
check_kernel
check_time
check_packages
check_logging

section "SUMMARY"
echo "  OK: $OK    WARN: $WARN    FAIL: $FAIL"
echo "  Review every WARN and FAIL above. This tool only reports - it changes nothing."
