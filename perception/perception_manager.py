from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Perception Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from perception.vision.vision_processor import VisionProcessor
from perception.audio.audio_processor import AudioProcessor
from perception.speech.speech_processor import SpeechProcessor
from perception.multimodal.multimodal_processor import MultimodalProcessor
from perception.sensors.sensor_manager import SensorManager


class PerceptionManager:
    """
    ==========================================
          HERCULE PERCEPTION MANAGER
    ==========================================

    Central perception hub.

    Responsible for:

    • Vision
    • Audio
    • Speech
    • Sensors
    • Multimodal Fusion

    Future

    • Camera Streams
    • Face Recognition
    • Object Detection
    • OCR
    • Gesture Recognition
    • Eye Tracking
    • Spatial Mapping
    • AR Processing
    """

    def __init__(self):

        ##################################################
        # PROCESSORS
        ##################################################

        self.vision = VisionProcessor()

        self.audio = AudioProcessor()

        self.speech = SpeechProcessor()

        self.multimodal = MultimodalProcessor()

        self.sensors = SensorManager()

    ##################################################
    # IMAGE
    ##################################################

    def process_image(

        self,

        image,

    ):

        return self.vision.process(

            image,

        )

    ##################################################

    def detect_objects(

        self,

        image,

    ):

        return self.vision.detect_objects(

            image,

        )

    ##################################################

    def detect_faces(

        self,

        image,

    ):

        return self.vision.detect_faces(

            image,

        )

    ##################################################

    def extract_text(

        self,

        image,

    ):

        return self.vision.ocr(

            image,

        )

    ##################################################
    # VISION (v1.1: structured local-vision observations)
    ##################################################

    def analyze_visual(
        self,
        source: str = "screenshot",
        path: str = "",
        prompt: str = "",
    ):
        """Explicit read-only visual analysis (screenshot/image-file).

        Delegates to perception.vision.manager.VisionManager; the legacy
        VisionProcessor methods above are untouched. Raises honestly
        (VisionUnavailable/ValueError) when uncapturable or model-less.
        """
        return self._vision_manager().analyze_screenshot(prompt or "") \
            if str(source or "").lower() == "screenshot" \
            else self._vision_manager().analyze_file(path, prompt or "")

    def _vision_manager(self):
        """Single persistent VisionManager (keeps last-observation state)."""
        manager = getattr(self, "_vision", None)
        if manager is None:
            from perception.vision.manager import VisionManager

            manager = VisionManager()
            self._vision = manager
        return manager

    def vision_snapshot(self):
        """Real HUD vision state (never fabricated observations)."""
        try:
            return self._vision_manager().snapshot()
        except Exception as exc:
            return {"state": "UNAVAILABLE", "ready": False,
                    "analyzing": False, "has_result": False,
                    "description": "", "confidence": 0.0,
                    "source": "", "model": "", "error": str(exc)[:200]}

    ##################################################
    # AUDIO
    ##################################################

    def process_audio(

        self,

        audio,

    ):

        return self.audio.process(

            audio,

        )

    ##################################################

    def classify_audio(

        self,

        audio,

    ):

        return self.audio.classify(

            audio,

        )

    ##################################################
    # SPEECH
    ##################################################

    def speech_to_text(

        self,

        audio,

    ):

        return self.speech.speech_to_text(

            audio,

        )

    ##################################################

    def text_to_speech(

        self,

        text,

    ):

        return self.speech.text_to_speech(

            text,

        )

    ##################################################
    # SENSORS
    ##################################################

    def register_sensor(

        self,

        name,

        sensor,

    ):

        self.sensors.register(

            name,

            sensor,

        )

    ##################################################

    def unregister_sensor(

        self,

        name,

    ):

        self.sensors.unregister(

            name,

        )

    ##################################################

    def read_sensor(

        self,

        name,

    ):

        return self.sensors.read(

            name,

        )

    ##################################################

    def read_all_sensors(self):

        return self.sensors.read_all()

    ##################################################
    # MULTIMODAL
    ##################################################

    def fuse(

        self,

        image=None,

        audio=None,

    ):

        vision_result = None

        audio_result = None

        speech_result = None

        sensor_result = self.sensors.read_all()

        if image is not None:

            vision_result = self.process_image(

                image,

            )

        if audio is not None:

            audio_result = self.process_audio(

                audio,

            )

            speech_result = self.speech_to_text(

                audio,

            )

        return self.multimodal.fuse(

            vision=vision_result,

            audio=audio_result,

            speech=speech_result,

            sensors=sensor_result,

        )

    ##################################################

    def summarize(

        self,

        fused_data,

    ):

        return self.multimodal.summarize(

            fused_data,

        )

    ##################################################
    # HEALTH
    ##################################################

    def health(self):

        return {

            "vision": True,

            "audio": True,

            "speech": True,

            "multimodal": True,

            "registered_sensors": len(

                self.sensors.names()

            ),

        }

    ##################################################
    # RESET
    ##################################################

    def reset(self):

        self.sensors.clear()

        self.multimodal.reset()

    ##################################################
    # FUTURE FEATURES
    ##################################################

    def start_camera(self):
        """
        Future:
        Start live camera stream.
        """
        pass

    ##################################################

    def stop_camera(self):
        """
        Future:
        Stop camera stream.
        """
        pass

    ##################################################

    def start_microphone(self):
        """
        Future:
        Start microphone capture.
        """
        pass

    ##################################################

    def stop_microphone(self):
        """
        Future:
        Stop microphone capture.
        """
        pass

    ##################################################

    def record_environment(self):
        """
        Future:
        Capture synchronized
        multimodal observations.
        """
        pass

    ##################################################

    def detect_gestures(self):
        """
        Future:
        Hand and body gesture recognition.
        """
        pass

    ##################################################

    def eye_tracking(self):
        """
        Future:
        Eye tracking for
        HERCULE Glasses.
        """
        pass

    ##################################################

    def spatial_mapping(self):
        """
        Future:
        Build 3D spatial maps.
        """
        pass