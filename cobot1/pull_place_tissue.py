"""독립 실행: 휴지 뽑아 놓기."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("pull_place_tissue", node_name="pull_place_tissue", args=args)
    print(f"[pull_place_tissue] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
