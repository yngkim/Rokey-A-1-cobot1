#!/bin/bash
# 로봇(192.168.1.100)과 같은 대역으로 PC 유선 IP 설정
# 사용: sudo ./set_robot_network.sh

set -euo pipefail

CONN_NAME="Wired connection 1"
PC_IP="192.168.1.10/24"
ROBOT_IP="192.168.1.100"

if [[ "${EUID}" -ne 0 ]]; then
  echo "sudo 권한이 필요합니다: sudo $0"
  exit 1
fi

echo "[1/3] 유선 IP를 ${PC_IP} 로 설정..."
nmcli connection modify "${CONN_NAME}" \
  ipv4.method manual \
  ipv4.addresses "${PC_IP}" \
  ipv4.gateway "" \
  ipv4.dns ""

echo "[2/3] 연결 재적용..."
nmcli connection down "${CONN_NAME}" || true
nmcli connection up "${CONN_NAME}"

sleep 2
echo "[3/3] 설정 확인"
ip -4 addr show enp2s0 | grep inet
echo "---"
ping -c 3 -W 2 "${ROBOT_IP}" || {
  echo "로봇(${ROBOT_IP}) ping 실패 — 이더넷 케이블/로봇 전원/IP를 확인하세요."
  exit 1
}

echo "완료: PC=${PC_IP%/*}, Robot=${ROBOT_IP}"
