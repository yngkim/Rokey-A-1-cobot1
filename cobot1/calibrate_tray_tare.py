"""독립 실행: 빈 트레이+식판 공차 측정·저장."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("calibrate_tray_tare", node_name="calibrate_tray_tare", args=args)
    print(f"[calibrate_tray_tare] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
