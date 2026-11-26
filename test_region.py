import os
from TTS.api import TTS


def test_coqui_voices():
    print("--- TESTING COQUI VOICES FOR HINGLISH ---")

    # Create folder
    os.makedirs("voice_samples", exist_ok=True)

    # Initialize Coqui TTS (It will download the model first time)
    # We use 'tts_models/en/ljspeech/tacotron2-DDC' which is fast and clear
    tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False)

    text = "Accha ji, main sun rahi hoon. Kya haal chaal hai?"

    # Coqui has many speakers, let's test a few common ones
    speakers = tts.speakers if hasattr(tts, 'speakers') else [None]

    # For simplicity, we'll just generate one sample with default voice
    try:
        print("Generating sample...")
        tts.tts_to_file(text=text, file_path="voice_samples/heart_coqui.wav")
        print("[SUCCESS] Saved: voice_samples/heart_coqui.wav")
    except Exception as e:
        print(f"[ERROR] {e}")


if __name__ == "__main__":
    test_coqui_voices()