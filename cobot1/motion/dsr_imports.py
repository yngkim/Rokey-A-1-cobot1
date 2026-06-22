"""DSR API import 헬퍼.

- posj, posx, posb : DR_common2 (좌표 타입)
- movej, movel, trans, fkin, ikin 등 : DSR_ROBOT2 (모션/서비스)
"""

from __future__ import annotations


def import_dsr_api():
    """DSR_ROBOT2 / DR_common2에서 올바른 심볼을 import합니다."""
    from DSR_ROBOT2 import (
        DR_BASE,
        DR_MV_MOD_ABS,
        DR_MV_MOD_REL,
        DR_TOOL,
        ROBOT_MODE_AUTONOMOUS,
        check_motion,
        fkin,
        get_current_posj,
        get_current_posx,
        get_external_torque,
        get_last_alarm,
        get_robot_state,
        get_tool_force,
        ikin,
        movec,
        movej,
        movejx,
        movel,
        mwait,
        set_accj,
        set_accx,
        set_robot_mode,
        set_tool_digital_output,
        set_velj,
        set_velx,
        trans,
    )
    from DR_common2 import posb, posj, posx

    return {
        "DR_BASE": DR_BASE,
        "DR_MV_MOD_ABS": DR_MV_MOD_ABS,
        "DR_MV_MOD_REL": DR_MV_MOD_REL,
        "DR_TOOL": DR_TOOL,
        "ROBOT_MODE_AUTONOMOUS": ROBOT_MODE_AUTONOMOUS,
        "check_motion": check_motion,
        "get_current_posj": get_current_posj,
        "get_current_posx": get_current_posx,
        "get_external_torque": get_external_torque,
        "get_last_alarm": get_last_alarm,
        "get_robot_state": get_robot_state,
        "get_tool_force": get_tool_force,
        "fkin": fkin,
        "ikin": ikin,
        "movec": movec,
        "movej": movej,
        "movejx": movejx,
        "movel": movel,
        "mwait": mwait,
        "set_accj": set_accj,
        "set_accx": set_accx,
        "set_robot_mode": set_robot_mode,
        "set_tool_digital_output": set_tool_digital_output,
        "set_velj": set_velj,
        "set_velx": set_velx,
        "trans": trans,
        "posb": posb,
        "posj": posj,
        "posx": posx,
    }
