import argparse
import ctypes
import os
import sys


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def show_error(message, title="Error"):
    ctypes.windll.user32.MessageBoxW(
        0,
        message,
        title,
        0x10  # MB_ICONERROR
    )


def _ensure_standard_streams():
    # PyInstaller's windowed build sets stdout/stderr to None. The audit writes
    # its durable progress to run.log; redirecting missing streams to NUL keeps
    # argparse and print calls from failing in the packaged executable.
    for stream_name in ("stdout", "stderr"):
        if getattr(sys, stream_name, None) is None:
            setattr(sys, stream_name, open(os.devnull, "w", encoding="utf-8"))


def main(argv=None):
    _ensure_standard_streams()
    arguments = list(sys.argv[1:] if argv is None else argv)
    app_flag_values = []
    remaining_arguments = []
    for argument in arguments:
        if argument.startswith("--start_audit_") and argument != "--start_audit_all":
            app_flag_values.append(argument.removeprefix("--start_audit_"))
        elif argument.startswith("--start-audit-") and argument != "--start-audit-all":
            app_flag_values.append(argument.removeprefix("--start-audit-"))
        else:
            remaining_arguments.append(argument)

    parser = argparse.ArgumentParser(
        description="WHAT Tools Control Center",
        allow_abbrev=False,
        epilog=(
            "Audit one tool with --start_audit APP_NAME or "
            "--start_audit_{app_name}; matching is case-insensitive."
        ),
    )
    parser.add_argument(
        "--start_audit_all",
        "--start-audit-all",
        dest="start_audit_all",
        action="store_true",
        help="Run the read-only performance audit on every tool in the current manifest.",
    )
    parser.add_argument(
        "--start_audit",
        "--start-audit",
        dest="start_audit_app",
        metavar="APP_NAME",
        help="Run the read-only performance audit on one configured tool.",
    )
    args = parser.parse_args(remaining_arguments)

    if len(app_flag_values) > 1:
        parser.error("specify only one app-specific --start_audit_{app_name} option")
    if app_flag_values and not app_flag_values[0].strip():
        parser.error("the app name in --start_audit_{app_name} cannot be empty")
    if args.start_audit_app is not None and not args.start_audit_app.strip():
        parser.error("the app name passed to --start_audit cannot be empty")
    if args.start_audit_app and app_flag_values:
        parser.error("specify the app name only once")
    if args.start_audit_all and (args.start_audit_app is not None or app_flag_values):
        parser.error("--start_audit_all cannot be combined with an app-specific audit option")

    if args.start_audit_all:
        from ui.audit_gateway import run_all_audits

        try:
            result = run_all_audits(progress=print)
        except Exception as exc:
            print(f"Audit gateway failed: {exc}", file=sys.stderr)
            return 2
        print(f"Audit summary: {result.summary_path}")
        print(f"Progress log: {result.log_path}")
        return result.exit_code

    app_name = (
        args.start_audit_app
        if args.start_audit_app is not None
        else (app_flag_values[0] if app_flag_values else None)
    )
    if app_name is not None:
        from ui.audit_gateway import run_app_audit

        try:
            result = run_app_audit(app_name, progress=print)
        except Exception as exc:
            print(f"Audit gateway failed: {exc}", file=sys.stderr)
            return 2
        print(f"Audit summary: {result.summary_path}")
        print(f"Progress log: {result.log_path}")
        return result.exit_code

    from ui.app import run_app

    run_app()
    return 0


if __name__ == "__main__":
    """
    if is_admin():
        show_error(
            "This application cannot be run as Administrator.\n\n"
            "Please restart it normally."
        )
        sys.exit(1)

    """

    sys.exit(main())
