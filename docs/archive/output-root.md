# Output Root and Permissions

Default export root is `/media/angelo/DRONE_DATA/SVO2_Frame_Export`. The GUI now allows changing the export root in case the default is not writable.

## If default path fails
- Ensure the USB stick is mounted at `/media/angelo/DRONE_DATA`.
- Set ownership/permissions so the current user can write:
  ```
  sudo chown -R angelo:angelo /media/angelo/DRONE_DATA
  ```
  (Adjust username as needed.)
- Alternatively, pick another writable directory via the "Export-Root" selector in the GUI.

The app performs a write test and will show a clear status if the chosen path is not writable.
