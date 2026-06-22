"""독립 실행: 충전기에서 스마트폰 가져오기."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("pick_from_charger", node_name="pick_from_charger", args=args)
    print(f"[pick_from_charger] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
