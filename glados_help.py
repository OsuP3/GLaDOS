def duration_msg(duration):
    if duration < 60:
        duration_msg = "a few seconds"
    elif (duration // 60 == 1):
        duration_msg = "a minute"
    elif (duration // 60) < 60:
        duration_msg = f"{int(duration//60)} minutes"
    elif (duration // 3600 == 1):
        duration_msg = f"an hour"
    elif (duration // 3600 < 24):
        duration_msg = f"{int(duration // 3600)} hours"
    elif ((duration // 3600) == 24):
        duration_msg = f"a day"
    else:
        duration_msg = f"{int(duration // (3600 * 24))} days"

    return duration_msg
