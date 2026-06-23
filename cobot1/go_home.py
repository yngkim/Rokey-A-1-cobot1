"""독립 실행: 홈 위치 복귀."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("go_home", node_name="go_home", args=args)
    print(f"[go_home] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
