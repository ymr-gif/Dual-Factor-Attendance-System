# Phone offload (Samsung S24 over USB) — ON HOLD

Status: notes only, not started (Cabucos, 18 Nov 2026). Do not build before the pilot.

## Why

The Acer Nitro 5 is away, and the MacBook Air 2016 (2 cores, 1.8 GHz) runs the pipeline
at about 5 fps. Face detection runs on every frame and takes most of that time. A phone
chip is faster, and has a GPU and an AI accelerator (NPU) the laptop lacks. The goal is
speed, so a port that only uses the phone's CPU is not enough.

First measure the MacBook with the newest-frame reader (build log, 18 Nov) and
`CAMERA_WIDTH=640` / `CAMERA_HEIGHT=480`. If the `[perception] N fps` line and the tap
verdicts are good enough, this stays on hold.

## The link

- An A-to-C data cable gives a network link with `adb forward` / `adb reverse` (TCP over
  USB). It works the same on Linux and macOS, needs USB debugging on the phone, and
  does not touch any Wi-Fi or school network.
- USB tethering also gives a network link on Linux. macOS has no built-in driver for
  it, so use adb there.
- The cable also charges the phone. Check that the laptop port keeps it charged under load.

## Where to split

The pipeline already hands its results over as events (`backend/perception.py`):
a face event carries `track_id`, `bbox`, `embedding`, `live_score`, `is_live`, `ts`, and
the matcher only reads those. So the phone can take over everything up to that point.

| Split | Phone does | Laptop does | Over the cable |
|---|---|---|---|
| A. Detector only | Detection on frames the laptop sends | Camera, tracking, recognition, liveness, matcher | One JPEG each way per frame |
| B. Whole perception | Camera (or frames from the laptop), detection, tracking, recognition, liveness | Matcher, DB, dashboard, Arduino | Face events (a 512-number embedding) and a small preview |

B moves the most work and sends the least data. If the phone's own camera is used, the
paper's camera changes (Ch 3 names the A4tech FHD 1080P), so frames from the laptop's
A4tech are the default.

## Using the AI chip

The PH S24 has an Exynos 2400 [CHECK the exact model on the phone]. Options, easiest first:

1. Termux with Python and onnxruntime: closest to the current code, CPU only, and
   onnxruntime and insightface are not packaged for Android in the usual way [CHECK].
   Does not meet the goal on its own.
2. A small Android app (Kotlin) with onnxruntime-android: the same `.onnx` models
   (buffalo_l `det_10g`, `w600k_r50`, MiniFASNet), run with the XNNPACK (CPU) or NNAPI
   (GPU/NPU) execution provider. NNAPI is deprecated from Android 15, so check what
   still runs on the NPU.
3. LiteRT (TensorFlow Lite) with the GPU delegate: needs the models converted to
   `.tflite`, and the embeddings checked against the laptop's (a converted model must
   give the same faces the same numbers, or every student re-enrolls).

## Checks before starting

- Embeddings from the phone must match the laptop's for the same face (cosine above
  0.99), or enrolled faces stop matching.
- Liveness scores must match too, or PC-025 calibration is redone on the phone.
- Heat: the phone throttles after minutes of full load. Measure fps after 30 minutes.
- Android may stop a background app. Keep it in the foreground with the screen on.
- Privacy (PC-023, D1): the phone stores no frame or embedding, and sends only over
  the cable.
- The paper's Materials list the laptop doing inference. A phone doing it is a paper
  change (Ch 3 Materials and Software), queued in the safe-paper repo as PC-047.
