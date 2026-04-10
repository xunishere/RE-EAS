"""Minimal runtime teardown with task-action success reporting."""

time.sleep(1)

print("task_action_total=%s" % task_action_total)
print("task_action_success=%s" % task_action_success)
print("task_action_failed=%s" % task_action_failed)
print("SR:%s" % task_sr)

try:
    database_runtime_dir = Path(os.getcwd())
    if str(database_runtime_dir) not in sys.path:
        sys.path.append(str(database_runtime_dir))
    from repair.database_runtime import append_record_if_qualified

    if repair_state and repair_state.get("enabled", False):
        task_dir = Path(__file__).resolve().parent
        append_result = append_record_if_qualified(
            executed_actions=list(repair_state.get("executed_actions", [])),
            environment=str(repair_state.get("environment", "")),
            task_description=str(repair_state.get("task_description", "")),
            sr_value=task_sr,
            monitor_trace_path=str(task_dir / "monitor_trace.csv"),
        )
        print("database_update=%s" % json.dumps(append_result, ensure_ascii=False))
except Exception as exc:
    print("Database maintenance skipped: %s" % exc)

try:
    finalize_visual_recording()
except Exception as exc:
    print("Visual recording finalization skipped: %s" % exc)

try:
    c.stop()
except Exception as exc:
    print("Failed to stop AI2-THOR controller:", exc)
