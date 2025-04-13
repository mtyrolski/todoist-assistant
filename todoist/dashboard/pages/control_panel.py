
import streamlit as st
from omegaconf import OmegaConf
from todoist.utils import Cache, load_config
from todoist.database.base import Database
import hydra
from todoist.automations.base import Automation
import io
import contextlib



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
            last_launch = launches[automation.name][-1].strftime("%Y-%m-%d %H:%M:%S")
        else:
            launch_count = 0
            last_launch = "Never"
        st.markdown(f"<div class='automation-details'><b>Last launch:</b> {last_launch}</div>", unsafe_allow_html=True)

        with st.expander(f"{automation.name}"):
            st.markdown(f"<span class='automation-title'>{automation.name}</span>", unsafe_allow_html=True)
            run_pressed = st.button("▶️ Run", key=automation.name)

            st.markdown(f"<div class='automation-details'><b>Launches:</b> {launch_count}</div>",
                        unsafe_allow_html=True)

            if run_pressed:
                with st.spinner("Executing automation..."):
                    stdout_capture = io.StringIO()
                    stderr_capture = io.StringIO()
                    with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                        automation.tick(dbio)
                    output = stdout_capture.getvalue()
                    error = stderr_capture.getvalue()
                    dbio.reset()
                st.success("Automation executed successfully!")

                # Display the captured output and error
                if output or error:
                    if output:
                        st.markdown("**Output:**")
                        st.text(output)
                    if error:
                        st.markdown("**Error:**")
                        st.text(error)

