"""Minimal AI2-THOR runtime for executing planner-generated code.

This runtime initializes the scene, exposes the basic action APIs used by
`code_plan.py`, and now attaches two lightweight sidecars:
- post-action RT-Lola monitoring
- pre-action safety prediction
"""

# Shared runtime state expected by generated plans.
recp_id = None
task_action_total = 0
task_action_success = 0
task_action_failed = 0
task_sr = 1
monitor_state = None
monitor_import_error = None
prediction_state = None
prediction_import_error = None
repair_state = None
repair_import_error = None
visual_task_dir = None
visual_recording_enabled = False
visual_frame_counter = 0
UNRECOVERABLE_REPAIR_EXIT_CODE = 42

try:
    monitor_module_dir = Path(os.getcwd()) / "data" / "aithor_connect"
    if str(monitor_module_dir) not in sys.path:
        sys.path.append(str(monitor_module_dir))
    from monitor_runtime import build_action_info, init_monitoring, record_post_action
except Exception as exc:
    build_action_info = None
    init_monitoring = None
    record_post_action = None
    monitor_import_error = exc

try:
    prediction_module_dir = Path(os.getcwd())
    if str(prediction_module_dir) not in sys.path:
        sys.path.append(str(prediction_module_dir))
    from data.aithor_connect.prediction_runtime import init_prediction_runtime, record_prediction
except Exception as exc:
    init_prediction_runtime = None
    record_prediction = None
    prediction_import_error = exc

try:
    repair_module_dir = Path(os.getcwd())
    if str(repair_module_dir) not in sys.path:
        sys.path.append(str(repair_module_dir))
    from data.aithor_connect.repair_runtime import (
        action_matches,
        begin_repair,
        end_repair,
        init_repair_runtime,
        record_executed_action,
        repair_allowed,
        request_repair,
        set_pending_skip_actions,
        should_skip_action,
    )
except Exception as exc:
    action_matches = None
    begin_repair = None
    end_repair = None
    init_repair_runtime = None
    record_executed_action = None
    repair_allowed = None
    request_repair = None
    set_pending_skip_actions = None
    should_skip_action = None
    repair_import_error = exc


def _ensure_robot_list(robot_or_robots):
    """Normalize single-robot and multi-robot inputs to a list."""
    if isinstance(robot_or_robots, list):
        return robot_or_robots
    return [robot_or_robots]


def _get_agent_id(robot):
    """Resolve the AI2-THOR agent id from the robot name."""
    return int(robot["name"][-1]) - 1


def _find_object_matches(pattern):
    """Return all object ids whose names match the provided pattern."""
    matches = []
    for obj in c.last_event.metadata["objects"]:
        object_id = obj["objectId"]
        if re.search(pattern, object_id):
            matches.append(obj)
    return matches


def _find_first_object(pattern):
    """Find the first non-degenerate object matching the pattern."""
    matches = _find_object_matches(pattern)
    for obj in matches:
        center = obj["axisAlignedBoundingBox"]["center"]
        if center != {"x": 0.0, "y": 0.0, "z": 0.0}:
            return obj
    if matches:
        return matches[0]
    raise ValueError("Cannot find object matching pattern: %s" % pattern)


def _sorted_target_matches(pattern, robot_or_robots):
    """Return matching objects sorted by current distance to the lead robot."""
    robots_list = _ensure_robot_list(robot_or_robots)
    agent_id = _get_agent_id(robots_list[0])
    agent_position = c.last_event.events[agent_id].metadata["agent"]["position"]
    matches = _find_object_matches(pattern)
    valid_matches = []
    for obj in matches:
        center = obj["axisAlignedBoundingBox"]["center"]
        if center == {"x": 0.0, "y": 0.0, "z": 0.0}:
            continue
        valid_matches.append(obj)
    if not valid_matches:
        return matches
    return sorted(
        valid_matches,
        key=lambda obj: distance_pts(
            [agent_position["x"], agent_position["y"], agent_position["z"]],
            [
                obj["axisAlignedBoundingBox"]["center"]["x"],
                obj["axisAlignedBoundingBox"]["center"]["y"],
                obj["axisAlignedBoundingBox"]["center"]["z"],
            ],
        ),
    )


def _recover_navigation_block(agent_id):
    """Try lightweight recovery moves before retrying navigation."""
    recovery_steps = [
        dict(action="RotateRight", degrees=45, agentId=agent_id),
        dict(action="MoveBack", agentId=agent_id),
        dict(action="RotateLeft", degrees=90, agentId=agent_id),
    ]
    any_success = False
    for step_kwargs in recovery_steps:
        try:
            event = _step_and_check(forceAction=True, **step_kwargs)
        except Exception:
            continue
        if event.metadata.get("lastActionSuccess", False):
            any_success = True
    return any_success


def _init_visual_recording(task_dir):
    """Prepare per-run image folders for execution playback."""
    global visual_task_dir
    global visual_recording_enabled
    global visual_frame_counter

    visual_task_dir = Path(task_dir)
    visual_frame_counter = 0
    visual_recording_enabled = True

    for folder_name in ("agent_1", "top_view"):
        folder_path = visual_task_dir / folder_name
        if folder_path.exists():
            shutil.rmtree(folder_path)
        folder_path.mkdir(parents=True, exist_ok=True)


def _capture_visual_frame(event=None):
    """Save one RGB frame for the agent view and top-view camera."""
    global visual_frame_counter

    if not visual_recording_enabled or visual_task_dir is None:
        return

    active_event = event if event is not None else c.last_event
    if active_event is None:
        return

    try:
        events = getattr(active_event, "events", None) or [active_event]
        if events:
            agent_frame = events[0].cv2img
            agent_path = visual_task_dir / "agent_1" / ("img_%05d.png" % visual_frame_counter)
            cv2.imwrite(str(agent_path), agent_frame)

        top_view_frames = getattr(events[0], "third_party_camera_frames", None) if events else None
        if top_view_frames:
            top_view_rgb = cv2.cvtColor(top_view_frames[-1], cv2.COLOR_BGR2RGB)
            top_view_path = visual_task_dir / "top_view" / ("img_%05d.png" % visual_frame_counter)
            cv2.imwrite(str(top_view_path), top_view_rgb)
    except Exception as exc:
        print("Visual capture skipped: %s" % exc)
        return

    visual_frame_counter += 1


def finalize_visual_recording(frame_rate=5):
    """Generate mp4 videos from the saved frame folders when possible."""
    if not visual_recording_enabled or visual_task_dir is None:
        return

    for folder_name in ("agent_1", "top_view"):
        folder_path = visual_task_dir / folder_name
        first_frame = folder_path / "img_00000.png"
        if not first_frame.exists():
            continue

        output_path = visual_task_dir / ("video_%s.mp4" % folder_name)
        command = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(frame_rate),
            "-i",
            str(folder_path / "img_%05d.png"),
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        try:
            subprocess.run(command, capture_output=True, text=True, check=False)
        except Exception as exc:
            print("Video generation skipped for %s: %s" % (folder_name, exc))


def _init_scene():
    """Initialize AI2-THOR scene and place the configured robots."""
    global c
    global reachable_positions
    global monitor_state
    global prediction_state
    global repair_state

    c = Controller(height=500, width=500)
    c.reset("FloorPlan" + str(floor_no))

    no_robot = len(robots)
    c.step(
        dict(
            action="Initialize",
            agentMode="default",
            snapGrid=False,
            gridSize=0.5,
            rotateStepDegrees=20,
            visibilityDistance=100,
            fieldOfView=90,
            agentCount=no_robot,
        )
    )

    try:
        camera_properties = c.step(action="GetMapViewCameraProperties")
        c.step(action="AddThirdPartyCamera", **camera_properties.metadata["actionReturn"])
    except Exception as exc:
        print("Top-view camera disabled: %s" % exc)

    reachable_positions_raw = c.step(action="GetReachablePositions").metadata["actionReturn"]
    reachable_positions = [(p["x"], p["y"], p["z"]) for p in reachable_positions_raw]

    for idx in range(no_robot):
        init_pos = random.choice(reachable_positions_raw)
        c.step(dict(action="Teleport", position=init_pos, agentId=idx))
        c.step(action="LookDown", degrees=35, agentId=idx)

    if init_monitoring is not None:
        try:
            task_dir = Path(__file__).resolve().parent
        except NameError:
            task_dir = Path(os.getcwd())
        _init_visual_recording(task_dir)
        monitor_state = init_monitoring(task_dir=str(task_dir), controller=c)
        if init_prediction_runtime is not None:
            try:
                prediction_state = init_prediction_runtime(task_dir=str(task_dir))
            except Exception as exc:
                prediction_state = None
                print("Prediction disabled: %s" % exc)
        elif prediction_import_error is not None:
            print("Prediction disabled: %s" % prediction_import_error)
        if init_repair_runtime is not None:
            try:
                repair_state = init_repair_runtime(
                    task_dir=str(task_dir),
                    environment="FloorPlan" + str(floor_no),
                    task_description=str(globals().get("task_description", "")),
                )
            except Exception as exc:
                repair_state = None
                print("Repair disabled: %s" % exc)
        elif repair_import_error is not None:
            print("Repair disabled: %s" % repair_import_error)
    elif monitor_import_error is not None:
        print("Monitoring disabled: %s" % monitor_import_error)

    _capture_visual_frame(c.last_event)


def _step_and_check(**kwargs):
    """Execute a single AI2-THOR action and surface runtime errors early."""
    event = c.step(**kwargs)
    if not event.metadata.get("lastActionSuccess", False):
        error_message = event.metadata.get("errorMessage", "")
        if error_message:
            print(error_message)
    _capture_visual_frame(event)
    return event


def _mark_task_action(success):
    """Update task-level execution statistics.

    Args:
        success: Whether the current task action succeeded.
    """
    global task_action_total
    global task_action_success
    global task_action_failed
    global task_sr

    task_action_total += 1
    if success:
        task_action_success += 1
    else:
        task_action_failed += 1
        task_sr = 0


def _record_monitoring(action_name, action_object, action_receptacle="0", throw_magnitude=0.0, success=True):
    """Record one completed planner-visible action for monitoring.

    Args:
        action_name: Planner-visible action label.
        action_object: Primary target object for the action.
        action_receptacle: Secondary receptacle target, or "0" when absent.
        throw_magnitude: Throw strength for ThrowObject actions.
    """
    if record_post_action is None or build_action_info is None:
        return

    action_info = build_action_info(
        action_name=action_name,
        action_object=action_object,
        action_receptacle=action_receptacle,
    )
    result = record_post_action(
        monitor_state=monitor_state,
        controller=c,
        action_info=action_info,
        throw_magnitude=throw_magnitude,
        action_success=success,
    )
    print("Monitor unsafe=%s" % result["unsafe"])


def _record_prediction(action_name, action_object, action_receptacle="0"):
    """Run one pre-action prediction from the cached current state."""
    if record_prediction is None or build_action_info is None or not monitor_state:
        return {
            "unsafe_probability": 0.0,
            "unsafe_label": 0,
            "confidence": 1.0,
            "prediction_set": [0],
        }

    pre_state = monitor_state.get("current_state")
    if not pre_state:
        return {
            "unsafe_probability": 0.0,
            "unsafe_label": 0,
            "confidence": 1.0,
            "prediction_set": [0],
        }

    action_info = build_action_info(
        action_name=action_name,
        action_object=action_object,
        action_receptacle=action_receptacle,
    )
    result = record_prediction(
        prediction_state=prediction_state,
        pre_state=pre_state,
        action_info=action_info,
    )
    print("Predict unsafe=%s prob=%s" % (result["unsafe_label"], result["unsafe_probability"]))
    return result


def _record_completed_action(action_name, action_object, action_receptacle="0", success=True):
    """Store one successfully completed planner-visible action for repair history."""
    if not success or record_executed_action is None or build_action_info is None:
        return
    action_info = build_action_info(
        action_name=action_name,
        action_object=action_object,
        action_receptacle=action_receptacle,
    )
    record_executed_action(repair_state, action_info)


def _dispatch_repair_action(repair_action):
    """Execute one repair action using the existing planner-visible APIs."""
    action_type = str(repair_action.get("type", ""))
    object_type = str(repair_action.get("objectType", ""))
    receptacle = str(repair_action.get("receptacle", "0") or "0")
    active_robot = globals().get("robot", robots[0])

    if action_type == "GoToObject":
        return GoToObject(active_robot, object_type)
    if action_type == "PickupObject":
        return PickupObject(active_robot, object_type)
    if action_type == "PutObject":
        return PutObject(active_robot, object_type, receptacle)
    if action_type == "OpenObject":
        return OpenObject(active_robot, object_type)
    if action_type == "CloseObject":
        return CloseObject(active_robot, object_type)
    if action_type == "SwitchOn":
        return SwitchOn(active_robot, object_type)
    if action_type == "SwitchOff":
        return SwitchOff(active_robot, object_type)
    if action_type == "SliceObject":
        return SliceObject(active_robot, object_type)
    if action_type == "BreakObject":
        return BreakObject(active_robot, object_type)
    if action_type == "ThrowObject":
        return ThrowObject(active_robot, object_type)
    raise ValueError("Unsupported repair action type: %s" % action_type)


def _coerce_action_success(result):
    """Normalize action wrapper returns into a boolean success flag."""
    if isinstance(result, bool):
        return result
    if result is None:
        return False
    metadata = getattr(result, "metadata", None)
    if isinstance(metadata, dict):
        return bool(metadata.get("lastActionSuccess", False))
    return False


def _should_skip_original_action(action_name, action_object, action_receptacle="0"):
    """Skip original plan actions that were already executed during repair."""
    if should_skip_action is None or build_action_info is None:
        return False
    if repair_state and int(repair_state.get("active_depth", 0)) > 0:
        return False
    action_info = build_action_info(
        action_name=action_name,
        action_object=action_object,
        action_receptacle=action_receptacle,
    )
    if should_skip_action(repair_state, action_info):
        print("Skipping original action already covered by repair: %s" % action_info)
        return True
    return False


def _maybe_execute_repair(action_name, action_object, action_receptacle, prediction_result):
    """Trigger constrained replanning instead of executing a blocked action."""
    if not prediction_result or int(prediction_result.get("unsafe_label", 0)) != 1:
        return False
    if request_repair is None or repair_allowed is None or build_action_info is None:
        return False
    if not repair_allowed(repair_state):
        return False

    action_info = build_action_info(
        action_name=action_name,
        action_object=action_object,
        action_receptacle=action_receptacle,
    )
    pre_state = monitor_state.get("current_state") if monitor_state else None
    if not pre_state:
        return False
    repair_result = request_repair(
        repair_state=repair_state,
        pre_state=pre_state,
        action_info=action_info,
        prediction_result=prediction_result,
    )
    if not repair_result or not repair_result.get("repair_actions"):
        if repair_result and repair_result.get("retry_required"):
            print("Retry required for unrecoverable unsafe action: %s" % action_info)
            raise SystemExit(UNRECOVERABLE_REPAIR_EXIT_CODE)
        return False

    print(
        "Replan replacing %s with %s actions"
        % (action_name, len(repair_result["repair_actions"]))
    )
    if set_pending_skip_actions is not None:
        set_pending_skip_actions(
            repair_state=repair_state,
            blocked_action={
                "type": action_name,
                "objectType": action_object,
                "receptacle": action_receptacle,
            },
            repair_actions=repair_result["repair_actions"],
        )
    begin_repair(repair_state)
    try:
        for repair_action in repair_result["repair_actions"]:
            print("Repair action: %s" % repair_action)
            action_success = _coerce_action_success(_dispatch_repair_action(repair_action))
            if not action_success:
                print("Repair aborted after failed action: %s" % repair_action)
                break
    finally:
        end_repair(repair_state)
    return True


def _execute_task_action(
    action_name,
    action_object,
    action_receptacle="0",
    throw_magnitude=0.0,
    **kwargs
):
    """Execute a planner-visible task action and record success statistics.

    Args:
        action_name: Planner-visible action label.
        action_object: Primary target object for monitoring data.
        action_receptacle: Secondary target receptacle for monitoring data.
        throw_magnitude: Throw strength when the action is ThrowObject.
        **kwargs: Arguments forwarded to `c.step`.

    Returns:
        The AI2-THOR event object.
    """
    if _should_skip_original_action(action_name, action_object, action_receptacle):
        return None
    prediction_result = _record_prediction(
        action_name=action_name,
        action_object=action_object,
        action_receptacle=action_receptacle,
    )
    if _maybe_execute_repair(action_name, action_object, action_receptacle, prediction_result):
        return None
    event = _step_and_check(**kwargs)
    success = event.metadata.get("lastActionSuccess", False)
    _mark_task_action(success)
    print("%s success=%s" % (action_name, success))
    _record_monitoring(
        action_name=action_name,
        action_object=action_object,
        action_receptacle=action_receptacle,
        throw_magnitude=throw_magnitude,
        success=success,
    )
    _record_completed_action(
        action_name=action_name,
        action_object=action_object,
        action_receptacle=action_receptacle,
        success=success,
    )
    return success


def GoToObject(robot_or_robots, dest_obj):
    """Navigate one or more robots to the closest reachable point near an object.

    Args:
        robot_or_robots: A robot dict or list of robot dicts.
        dest_obj: Target object name or object id regex.

    Returns:
        None

    Exceptions:
        ValueError: Raised when the target object cannot be resolved.
    """
    global recp_id

    if _should_skip_original_action("GoToObject", dest_obj):
        return

    prediction_result = _record_prediction("GoToObject", dest_obj)
    if _maybe_execute_repair("GoToObject", dest_obj, "0", prediction_result):
        return

    action_success = True
    robots_list = _ensure_robot_list(robot_or_robots)
    target_candidates = _sorted_target_matches(dest_obj, robots_list)
    if not target_candidates:
        raise ValueError("Cannot find object matching pattern: %s" % dest_obj)

    target_id = None
    target_pos = None
    reached_target = False

    for target_obj in target_candidates[:5]:
        target_id = target_obj["objectId"]
        target_center = target_obj["axisAlignedBoundingBox"]["center"]
        target_pos = [target_center["x"], target_center["y"], target_center["z"]]

        distances = [10.0] * len(robots_list)
        prev_distances = [10.0] * len(robots_list)
        stalled_counts = [0] * len(robots_list)
        closest_offsets = [0] * len(robots_list)
        goal_points = closest_node(target_pos, reachable_positions, len(robots_list), closest_offsets)
        loop_guard = 0

        while all(distance > 0.25 for distance in distances):
            loop_guard += 1
            if loop_guard > 220:
                action_success = False
                break

            candidate_failed = False
            for idx, robot in enumerate(robots_list):
                agent_id = _get_agent_id(robot)
                metadata = c.last_event.events[agent_id].metadata
                location = metadata["agent"]["position"]

                prev_distances[idx] = distances[idx]
                distances[idx] = distance_pts(
                    [location["x"], location["y"], location["z"]],
                    goal_points[idx],
                )

                if abs(distances[idx] - prev_distances[idx]) < 0.1:
                    stalled_counts[idx] += 1
                else:
                    stalled_counts[idx] = 0

                if stalled_counts[idx] >= 6:
                    closest_offsets[idx] += 1
                    stalled_counts[idx] = 0
                    if closest_offsets[idx] >= 6:
                        if not _recover_navigation_block(agent_id):
                            candidate_failed = True
                            action_success = False
                            break
                    goal_points = closest_node(target_pos, reachable_positions, len(robots_list), closest_offsets)

                nav_event = c.step(
                    dict(
                        action="ObjectNavExpertAction",
                        position=dict(
                            x=goal_points[idx][0],
                            y=goal_points[idx][1],
                            z=goal_points[idx][2],
                        ),
                        agentId=agent_id,
                    )
                )
                next_action = nav_event.metadata.get("actionReturn")
                if next_action is None:
                    stalled_counts[idx] += 2
                    continue

                step_event = _step_and_check(action=next_action, agentId=agent_id, forceAction=True)
                if not step_event.metadata.get("lastActionSuccess", False):
                    stalled_counts[idx] += 2
                    action_success = False
                    error_message = step_event.metadata.get("errorMessage", "")
                    if "blocking" in error_message.lower():
                        _recover_navigation_block(agent_id)

            if candidate_failed:
                break

            time.sleep(0.05)

        if all(distance <= 0.25 for distance in distances):
            reached_target = True
            break

    if not reached_target:
        action_success = False

    # Face the target after reaching its neighborhood to improve interaction success.
    if reached_target and target_pos is not None:
        anchor_robot = robots_list[0]
        agent_id = _get_agent_id(anchor_robot)
        metadata = c.last_event.events[agent_id].metadata
        robot_position = metadata["agent"]["position"]
        robot_rotation = metadata["agent"]["rotation"]["y"]
        vector_to_target = np.array(
            [target_pos[0] - robot_position["x"], target_pos[2] - robot_position["z"]]
        )
        if np.linalg.norm(vector_to_target) > 0:
            unit_y = np.array([0.0, 1.0])
            unit_vector = vector_to_target / np.linalg.norm(vector_to_target)
            angle = math.degrees(math.atan2(np.linalg.det([unit_vector, unit_y]), np.dot(unit_vector, unit_y)))
            angle = (angle + 360.0) % 360.0
            rotation_delta = angle - robot_rotation
            if rotation_delta > 0:
                rotate_event = _step_and_check(action="RotateRight", degrees=abs(rotation_delta), agentId=agent_id)
            else:
                rotate_event = _step_and_check(action="RotateLeft", degrees=abs(rotation_delta), agentId=agent_id)
            if not rotate_event.metadata.get("lastActionSuccess", False):
                action_success = False

    if dest_obj in ("Cabinet", "Fridge", "CounterTop", "SinkBasin", "Microwave") and target_id is not None:
        recp_id = target_id

    _mark_task_action(action_success)
    print("GoToObject success=%s" % action_success)
    _record_monitoring("GoToObject", dest_obj, success=action_success)
    _record_completed_action("GoToObject", dest_obj, success=action_success)
    return action_success


def PickupObject(robot_or_robots, pick_obj):
    """Pick up the requested object with one or more robots."""
    robots_list = _ensure_robot_list(robot_or_robots)
    target_obj = _find_first_object(pick_obj)
    target_id = target_obj["objectId"]

    for robot in robots_list:
        return _execute_task_action(
            "PickupObject",
            action_object=pick_obj,
            action="PickupObject",
            objectId=target_id,
            agentId=_get_agent_id(robot),
            forceAction=True,
        )


def PutObject(robot, put_obj, recp):
    """Put the currently held object into or onto a receptacle."""
    receptacle_candidates = _find_object_matches(recp)
    if not receptacle_candidates:
        raise ValueError("Cannot find receptacle matching pattern: %s" % recp)

    receptacle = min(
        receptacle_candidates,
        key=lambda item: item.get("distance", float("inf")),
    )
    return _execute_task_action(
        "PutObject",
        action_object=put_obj,
        action_receptacle=recp,
        action="PutObject",
        objectId=receptacle["objectId"],
        agentId=_get_agent_id(robot),
        forceAction=True,
    )


def SwitchOn(robot, sw_obj):
    """Switch on a toggleable object."""
    candidates = _find_object_matches(sw_obj)
    if sw_obj == "StoveKnob":
        if _should_skip_original_action("SwitchOn", sw_obj):
            return
        prediction_result = _record_prediction("SwitchOn", sw_obj)
        if _maybe_execute_repair("SwitchOn", sw_obj, "0", prediction_result):
            return
        action_success = True
        for obj in candidates:
            event = _step_and_check(
                action="ToggleObjectOn",
                objectId=obj["objectId"],
                agentId=_get_agent_id(robot),
                forceAction=True,
            )
            if not event.metadata.get("lastActionSuccess", False):
                action_success = False
            time.sleep(0.1)
        _mark_task_action(action_success)
        print("SwitchOn success=%s" % action_success)
        _record_monitoring("SwitchOn", sw_obj, success=action_success)
        _record_completed_action("SwitchOn", sw_obj, success=action_success)
        return action_success

    if not candidates:
        raise ValueError("Cannot find switchable object matching pattern: %s" % sw_obj)
    return _execute_task_action(
        "SwitchOn",
        action_object=sw_obj,
        action="ToggleObjectOn",
        objectId=candidates[0]["objectId"],
        agentId=_get_agent_id(robot),
        forceAction=True,
    )


def SwitchOff(robot, sw_obj):
    """Switch off a toggleable object."""
    candidates = _find_object_matches(sw_obj)
    if sw_obj == "StoveKnob":
        if _should_skip_original_action("SwitchOff", sw_obj):
            return
        prediction_result = _record_prediction("SwitchOff", sw_obj)
        if _maybe_execute_repair("SwitchOff", sw_obj, "0", prediction_result):
            return
        action_success = True
        for obj in candidates:
            event = _step_and_check(
                action="ToggleObjectOff",
                objectId=obj["objectId"],
                agentId=_get_agent_id(robot),
                forceAction=True,
            )
            if not event.metadata.get("lastActionSuccess", False):
                action_success = False
            time.sleep(0.1)
        _mark_task_action(action_success)
        print("SwitchOff success=%s" % action_success)
        _record_monitoring("SwitchOff", sw_obj, success=action_success)
        _record_completed_action("SwitchOff", sw_obj, success=action_success)
        return action_success

    if not candidates:
        raise ValueError("Cannot find switchable object matching pattern: %s" % sw_obj)
    return _execute_task_action(
        "SwitchOff",
        action_object=sw_obj,
        action="ToggleObjectOff",
        objectId=candidates[0]["objectId"],
        agentId=_get_agent_id(robot),
        forceAction=True,
    )


def OpenObject(robot, sw_obj):
    """Open an interactable object."""
    global recp_id

    target_id = _find_first_object(sw_obj)["objectId"]
    recp_id = target_id

    return _execute_task_action(
        "OpenObject",
        action_object=sw_obj,
        action="OpenObject",
        objectId=target_id,
        agentId=_get_agent_id(robot),
        forceAction=True,
    )


def CloseObject(robot, sw_obj):
    """Close an interactable object."""
    global recp_id

    target_id = _find_first_object(sw_obj)["objectId"]

    result = _execute_task_action(
        "CloseObject",
        action_object=sw_obj,
        action="CloseObject",
        objectId=target_id,
        agentId=_get_agent_id(robot),
        forceAction=True,
    )
    recp_id = None
    return result


def BreakObject(robot, sw_obj):
    """Break the target object."""
    target = _find_first_object(sw_obj)
    return _execute_task_action(
        "BreakObject",
        action_object=sw_obj,
        action="BreakObject",
        objectId=target["objectId"],
        agentId=_get_agent_id(robot),
        forceAction=True,
    )


def SliceObject(robot, sw_obj):
    """Slice the target object."""
    target = _find_first_object(sw_obj)
    return _execute_task_action(
        "SliceObject",
        action_object=sw_obj,
        action="SliceObject",
        objectId=target["objectId"],
        agentId=_get_agent_id(robot),
        forceAction=True,
    )


def ThrowObject(robot, sw_obj, moveMagnitude=7):
    """Throw the currently held object."""
    return _execute_task_action(
        "ThrowObject",
        action_object=sw_obj,
        throw_magnitude=moveMagnitude,
        action="ThrowObject",
        moveMagnitude=moveMagnitude,
        agentId=_get_agent_id(robot),
        forceAction=True,
    )


_init_scene()
