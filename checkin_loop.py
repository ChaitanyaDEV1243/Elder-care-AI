import time
import json
import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel
from dotenv import load_dotenv
import os
from google import genai
from checkin_questions import QUESTIONS

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
model = WhisperModel("small", device="cpu")

def ask_and_record(index, duration=5, samplerate=16000):
    question = QUESTIONS[index]
    print(f"\nQuestion {index+1}: {question}")
    # TODO once voice is finalized: play the question's audio clip here before recording

    print("Recording in 3... 2... 1...")
    start_time = time.time()
    audio = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1)
    sd.wait()
    response_latency = round(time.time() - start_time, 2)

    filename = f"answer_{index+1}.wav"
    sf.write(filename, audio, samplerate)

    segments, _ = model.transcribe(filename, language="hi")
    transcript = " ".join(seg.text for seg in segments)
    print("Transcript:", transcript)
    return transcript, response_latency

def analyze_response(transcript, index):
    prompt = f"""Analyze this response to a wellbeing check-in question for an elderly person.
Question: {QUESTIONS[index]}
Response (Hindi): {transcript}

Return ONLY valid JSON in exactly this shape, nothing else, no markdown formatting:
{{"sentiment_score": <number between -1 and 1>, "medication_confirmed": "<yes, no, or not_applicable>"}}"""
    response = client.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=prompt
    )
    text = response.text.strip().strip("```json").strip("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"WARNING: Gemini returned unparseable output: {text}")
        return {"sentiment_score": 0.0, "medication_confirmed": "not_applicable"}

if __name__ == "__main__":
    results = []

    for i in range(len(QUESTIONS)):
        transcript, latency = ask_and_record(i)
        analysis = analyze_response(transcript, i)
        record = {
            "question_index": i,
            "transcript": transcript,
            "response_latency": latency,
            "sentiment_score": float(analysis["sentiment_score"]),
            "medication_confirmed": analysis["medication_confirmed"],
            "call_answered": True
        }
        results.append(record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        print("---")

    with open("checkin_output.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)