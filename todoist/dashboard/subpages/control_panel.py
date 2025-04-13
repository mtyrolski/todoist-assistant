
import streamlit as st
from omegaconf import OmegaConf
from todoist.utils import Cache, load_config
from loguru import logger
from todoist.database.base import Database
import hydra
from todoist.automations.base import Automation
import io
import contextlib
import datetime

def render_control_panel_page(dbio: Database) -> None:
    config: OmegaConf = load_config('automations', '../configs')
    automations: list[Automation] = hydra.utils.instantiate(config.automations)

    st.title("Automation Control Panel")
    st.write("Manage and execute your automations below:")

    # Add some custom CSS for a better appearance
    st.markdown("""
        <style>
        .automation-box {
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 10px;
            margin-bottom: 10px;
            background-color: #fff;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }
        .automation-title {
            font-weight: bold;
            color: #333;
        }
        .automation-details {
            margin-top: 10px;
            margin-bottom: 10px;
        }
        .automation-output {
            background-color: #f9f9f9;
            border-radius: 5px;
            padding: 10px;
            margin-top: 10px;
        }
        </style>
        """,
                unsafe_allow_html=True)

    for automation in automations:
        cache = Cache()
        launches = cache.automation_launches.load()
        if automation.name in launches:
            launch_count = len(launches[automation.name])
            detailed_last_launch = launches[automation.name][-1].strftime("%Y-%m-%d %H:%M:%S")
            last_launch_time = launches[automation.name][-1]
            delta = datetime.datetime.now() - last_launch_time
            days = delta.days
            hours = delta.seconds // 3600
            header_last_launch = f"{days}d {hours}h"
        else:
            launch_count = 0
            detailed_last_launch = "Never"
            header_last_launch = "Never launched"

        header_last_launch = f'launched {header_last_launch} ago' if launch_count > 0 else 'Never launched'

        with st.expander(f"{automation.name} ({header_last_launch})", expanded=False):
            st.markdown(f"<span class='automation-title'>{automation.name}</span>", unsafe_allow_html=True)
            st.markdown(f"<div class='automation-details'><b>Last launch:</b> {detailed_last_launch}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='automation-details'><b>Launches:</b> {launch_count}</div>", unsafe_allow_html=True)

            run_pressed = st.button("▶️ Run", key=automation.name)

            if run_pressed:
                with st.spinner("Executing automation..."):
                    output_placeholder = st.empty()  # Create a placeholder for streaming output

                    # Capture all outputs (stdout, stderr, and loguru logs)
                    output_stream = io.StringIO()
                    loguru_handler_id = logger.add(output_stream, format="{message}", level="DEBUG")

                    try:
                        with contextlib.redirect_stdout(output_stream), contextlib.redirect_stderr(output_stream):
                            automation.tick(dbio)  # Execute the automation

                            # Continuously update the placeholder with the captured output
                            while True:
                                output = output_stream.getvalue()
                                if output:
                                    output_placeholder.text(output)
                                    output_stream.truncate(0)
                                    output_stream.seek(0)
                                else:
                                    break
                    finally:
                        # Remove the loguru handler to avoid duplicate logs
                        logger.remove(loguru_handler_id)

                    dbio.reset()

                st.success("Automation executed successfully!")