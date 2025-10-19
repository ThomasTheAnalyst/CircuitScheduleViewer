# CircuitScheduleViewer
# Mota Plotter

Mota Plotter is a Python tool (designed for Google Colab or Jupyter)
to visualize the behavior and configuration of 'Clickiemota' devices via the Clickie API.

Its main functions are:
1.  **Fetch Configuration:** Connects to the Clickie API to retrieve the
    active JSON configuration for a specified device.
2.  **Parse & Plot Behavior:** Interprets the JSON schedule and plots the
    *actual* ON/OFF state of each relay for a selected date range.
3.  **Plot Configuration:** Generates a second chart showing the *programmed*
    weekly schedule for each relay.
4.  **Generate Alerts:** Compares actual behavior against the schedule and
    prints alerts for discrepancies.
5.  **Integrate with G-Suite:** Includes functions to upload the generated
    plot to a specific Google Drive folder and log the action as a "ticket"
    in a specific Google Sheet.

**NOTE FOR REPOSITORY USE:**
This script is ready to run, but you must fill in the placeholder
variables in the '--- USER CONFIGURATION ---' section below.
These include API credentials, client/company IDs, and G-Suite IDs.
"""
