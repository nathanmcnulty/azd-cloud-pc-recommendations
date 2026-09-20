"""Azure Functions entry point for the Cloud PC recommendations monitor."""

import logging

import azure.functions as func

from cloudpc_monitor.service import MonitorService


app = func.FunctionApp()


@app.function_name(name="CloudPcRecommendations")
@app.timer_trigger(
    schedule="%MONITOR_SCHEDULE%",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def cloud_pc_recommendations(timer: func.TimerRequest) -> None:
    """Collect Cloud PC signals, evaluate rules, and persist the audit report."""

    if timer.past_due:
        logging.warning("The Cloud PC monitor timer invocation is past due.")

    report = MonitorService.from_environment().run()
    logging.info(
        "Cloud PC monitor completed: runId=%s cloudPcs=%s alerts=%s notifications=%s",
        report["runId"],
        report["collection"]["cloudPcCount"],
        report["alertCount"],
        report["notifications"]["status"],
    )
