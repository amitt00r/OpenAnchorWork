# Adding a camera

OpenAnchorWork only shows cameras that have a profile. Adding a model takes three steps.

## 1. Add a profile

In [`profiles.py`](../profiles.py), describe the camera and add it to `PROFILES`:

```python
ANKER_EXAMPLE = Profile(
    key="anker-example",          # stable id, also names the settings file
    name="Anker PowerConf Example",
    vid="291a", pid="xxxx",       # from `lsusb`
    fov_zoom={},                  # FOV preset (degrees) -> zoom_absolute, if it has presets
    hdr=False,                    # Anker HDR switch (selector 19)
    orientation=False,            # mirror / upside down (selector 17)
    raw_auto_exposure=False,      # True if auto exposure can't be re-enabled through V4L2
    pickup_modes=(),              # ((value, label), ...) for mic Pick-Up Mode (selector 16)
    stream_reset_keys=(),         # standard controls the firmware resets at stream start
)

PROFILES = (ANKER_C200, ANKER_EXAMPLE)
```

Turn on only the features you have verified on that camera. Anything left off is hidden in the app.

## 2. Allow USB access

If the camera needs raw USB access (`raw_auto_exposure=True`), add a line for its USB ID to
[`system/70-openanchorwork.rules`](../system/70-openanchorwork.rules).

## 3. Verify on hardware

Different Anker models use different vendor selectors. Before enabling a feature:

* Check that the selector exists: `GET_LEN` should return the expected size (60 on the C200).
* Change the setting and confirm the effect on real video or audio, not just a read-back. On the C200, several
  selectors accept writes and read them back without doing anything.
* **Never write selector 13**: it resets the camera to factory settings.

[PROTOCOL.md](PROTOCOL.md) describes how the C200's commands were decoded and the quirks found. Please
include what you tested in your pull request.
