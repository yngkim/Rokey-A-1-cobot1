"""독립 실행: 충전기에 스마트폰 놓기."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("place_on_charger", node_name="place_on_charger", args=args)
    print(f"[place_on_charger] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
