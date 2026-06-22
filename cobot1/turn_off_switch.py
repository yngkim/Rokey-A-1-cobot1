"""독립 실행: 스위치 끄기."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("turn_off_switch", node_name="turn_off_switch", args=args)
    print(f"[turn_off_switch] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
