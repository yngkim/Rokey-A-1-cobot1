"""페트병 뚜껑 열기 — 티칭 시작 조인트 → 그리퍼 닫기 → TCP 수직 하강 → 비틀기."""

from __future__ import annotations

from cobot1.tasks.base import BaseTask


class OpenBottleTask(BaseTask):
    name = "open_bottle"

    def _execute(self) -> None:
        cfg = self._cfg
        motion = self._motion
        task = self.name

        home_joint = list(self._scenarios["motion"]["home_joint"])
        start_joint = list(
            cfg.get(
                "start_joint",
                [0.29, 1.68, 74.79, -0.04, 103.54, 10.21],
            )
        )
        motion.set_recovery_joint(home_joint)

        bottle = list(cfg["bottle_pose"])
        cap_place = list(cfg["cap_place_pose"])
        place_approach_z = float(cfg["cap_place_approach_z_mm"])
        place_depth = float(cfg["cap_place_depth_mm"])
        torque_threshold = float(cfg.get("contact_force_z_threshold", 8.0))
        contact_retreat = float(cfg.get("contact_retreat_mm", 5.0))
        grasp_offset_z = float(cfg.get("cap_touch_to_grasp_z_mm", 0.0))
        probe_vel = cfg.get("probe_vel", [15, 10])
        probe_acc = cfg.get("probe_acc", [30, 15])
        probe_fine_vel = cfg.get("probe_fine_vel", [6, 4])
        probe_fine_acc = cfg.get("probe_fine_acc", [12, 8])

        cap_anchor: list[float] = []

        def _release_compliance() -> None:
            try:
                from cobot1.motion.dsr_imports import import_dsr_api

                import_dsr_api()["release_compliance_ctrl"]()
            except Exception:
                pass

        def _prepare_start() -> None:
            """티칭 시작 조인트로 이동 (홈에서 툴 수직 올린 자세, 자세 유지)."""
            _release_compliance()
            motion.clear_cancel()
            motion.gripper.open()
            motion.movej_joint(start_joint, "move_start_joint", task)

        def _find_and_grasp_cap() -> None:
            """시작 TCP 앵커 고정 → 그리퍼 닫기 → 베이스 Z만 하강 → 잡기."""
            cap_anchor[:] = motion.get_current_tcp_pose()

            motion.safety.begin_contact_search()
            try:
                motion.gripper.close()
                motion.interruptible_sleep(
                    float(cfg.get("contact_settle_sec", 0.4))
                )
                baseline_vector = motion.safety.sample_force_baseline(
                    samples=int(cfg.get("contact_baseline_samples", 8)),
                    interval_sec=float(cfg.get("contact_baseline_interval_sec", 0.05)),
                )

                contact_z, touch_force_z = motion.probe_down_until_contact(
                    task,
                    cap_anchor,
                    baseline_vector=baseline_vector,
                    force_threshold_z=torque_threshold,
                    max_travel_mm=float(cfg.get("search_max_descent_mm", 130.0)),
                    step_mm=float(cfg.get("contact_step_mm", 0.5)),
                    coarse_step_mm=float(cfg.get("contact_coarse_step_mm", 2.0)),
                    coarse_travel_mm=float(cfg.get("contact_coarse_travel_mm", 60.0)),
                    max_force_z=float(cfg.get("contact_max_force_z", 22.0)),
                    vel=probe_vel,
                    acc=probe_acc,
                    fine_vel=probe_fine_vel,
                    fine_acc=probe_fine_acc,
                )

                motion.publish_status(
                    task,
                    "contact_detected",
                    "done",
                    f"접촉 감지 (ΔFz={touch_force_z:.1f})",
                    extra={"touch_force_z": touch_force_z, "contact_z_mm": contact_z},
                )

                lift_z = contact_z + max(
                    contact_retreat,
                    float(cfg.get("gripper_open_clearance_mm", 20.0)),
                )
                motion.move_vertical_to_z(
                    lift_z,
                    cap_anchor,
                    "lift_for_gripper_open",
                    task,
                    vel=probe_vel,
                    acc=probe_acc,
                )

                motion.gripper.open()

                grasp_z = contact_z + grasp_offset_z
                motion.move_vertical_to_z(
                    grasp_z,
                    cap_anchor,
                    "align_cap_grasp",
                    task,
                    vel=probe_vel,
                    acc=probe_acc,
                )
                motion.gripper.close()
                cap_anchor[2] = grasp_z
            finally:
                motion.safety.end_contact_search()

            motion.publish_status(
                task,
                "cap_grasped",
                "done",
                f"뚜껑 잡기 (접촉Z={contact_z:.1f}, graspZ={grasp_z:.1f})",
                extra={"contact_z_mm": contact_z, "grasp_z_mm": grasp_z},
            )

        def _grasp_cap_at_taught_pose() -> None:
            approach_z = float(cfg["cap_approach_z_mm"])
            grasp_z = float(cfg["cap_grasp_z_mm"])
            motion.gripper.open()
            motion.approach_pose(bottle, approach_z, "approach_bottle", task)
            cap_anchor[:] = motion.get_current_tcp_pose()
            motion.move_vertical_to_z(
                grasp_z,
                cap_anchor,
                "descend_to_cap",
                task,
                vel=probe_vel,
                acc=probe_acc,
            )
            motion.gripper.close()
            cap_anchor[2] = grasp_z

        grasp_cap = (
            _grasp_cap_at_taught_pose
            if cfg.get("use_contact_search") is False
            else _find_and_grasp_cap
        )

        def _press_down() -> None:
            if not cap_anchor:
                raise RuntimeError("cap_anchor 미설정")
            cap_anchor[2] -= float(cfg["twist_down_mm"])
            motion.move_vertical_to_z(
                cap_anchor[2],
                cap_anchor,
                "press_down",
                task,
                vel=probe_vel,
                acc=probe_acc,
            )

        def _lift_cap() -> None:
            if not cap_anchor:
                raise RuntimeError("cap_anchor 미설정")
            cap_anchor[2] += float(cfg["cap_lift_mm"])
            motion.move_vertical_to_z(
                cap_anchor[2],
                cap_anchor,
                "lift_cap",
                task,
                vel=probe_vel,
                acc=probe_acc,
            )

        def _place_cap_down() -> None:
            place_anchor = list(cap_place)
            place_z = float(cap_place[2]) + place_depth
            motion.move_vertical_to_z(
                place_z,
                place_anchor,
                "place_cap_down",
                task,
                vel=probe_vel,
                acc=probe_acc,
            )

        def _home_finish() -> None:
            """시작 조인트(들어올린 자세) → 홈 조인트 순으로 복귀."""
            motion.movej_joint(start_joint, "return_start_joint", task)
            motion.movej_joint(home_joint, "home_finish", task)

        steps = [
            ("prepare_start", _prepare_start),
            ("find_cap_height", grasp_cap),
            ("press_down", _press_down),
            (
                "twist_open",
                lambda: motion.rotate_tool_z_steps(
                    float(cfg["twist_angle_deg"]),
                    int(cfg["twist_steps"]),
                    "twist",
                    task,
                    pause_sec=0.2,
                ),
            ),
            ("lift_cap", _lift_cap),
            (
                "move_cap_place",
                lambda: motion.approach_pose(
                    cap_place, place_approach_z, "move_cap_place", task
                ),
            ),
            ("place_cap_down", _place_cap_down),
            ("release_cap", motion.gripper.open),
            (
                "retract_from_place",
                lambda: motion.retreat_base_z(
                    place_approach_z, "retract_from_place", task
                ),
            ),
            ("home_finish", _home_finish),
        ]
        motion.run_sequence(task, steps)
