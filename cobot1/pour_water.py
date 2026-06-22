"""독립 실행: 물 따르기."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("pour_water", node_name="pour_water", args=args)
    print(f"[pour_water] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
