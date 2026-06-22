"""독립 실행: 알약 픽앤플레이스."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("pick_place_pill", node_name="pick_place_pill", args=args)
    print(f"[pick_place_pill] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
