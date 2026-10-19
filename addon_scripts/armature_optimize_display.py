from hitori_addon.arm import selected_arms

for arm in selected_arms():
    arm.data.display_type = "STICK"
    arm.display_type = "BOUNDS"
    arm.show_in_front = True
