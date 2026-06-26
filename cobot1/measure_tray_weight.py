"""독립 실행: 식판 무게 측정 (식전/식후)."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("measure_tray_weight", node_name="measure_tray_weight", args=args)
    print(f"[measure_tray_weight] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
