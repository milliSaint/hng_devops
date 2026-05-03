"""
IP blocker using iptables.

Inserts DROP rules into the INPUT chain. The detector container must run
with cap_add: NET_ADMIN and network_mode: host for these rules to affect
the actual host network.
"""
import logging
import os
import subprocess


logger = logging.getLogger(__name__)


def block_ip(ip: str):
    """Insert an iptables DROP rule for ip. Idempotent — check before insert."""
    if _rule_exists(ip):
        return
    try:
        subprocess.run(
            ["iptables", "-I", "INPUT", "-s", ip, "-j", "DROP"],
            check=True, capture_output=True, text=True
        )
        logger.info("Blocked %s via iptables", ip)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to block %s: %s", ip, e.stderr)


def unblock_ip(ip: str):
    """Remove the iptables DROP rule for ip."""
    if not _rule_exists(ip):
        return
    try:
        subprocess.run(
            ["iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"],
            check=True, capture_output=True, text=True
        )
        logger.info("Unblocked %s via iptables", ip)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to unblock %s: %s", ip, e.stderr)


def _rule_exists(ip: str) -> bool:
    result = subprocess.run(
        ["iptables", "-C", "INPUT", "-s", ip, "-j", "DROP"],
        capture_output=True
    )
    return result.returncode == 0
