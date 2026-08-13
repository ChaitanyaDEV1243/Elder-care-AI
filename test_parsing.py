from checkin_loop import analyze_response

fake_transcript = ""
result = analyze_response(fake_transcript, 1)
print(result)
print(type(result))