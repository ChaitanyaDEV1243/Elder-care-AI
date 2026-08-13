# Elder-care-AI



\## Demo persona



Ram Prakash Verma, 68, lives alone in a small town in Uttar Pradesh. Son works in Bangalore, calls occasionally, not daily. On morning and evening BP medication, mild arthritis slows him down.



Fourteen days of simulated check-ins: days 1-11 are baseline (medication mostly confirmed, neutral-to-positive sentiment, 2-4 second response latency), day 12 misses evening medication, day 13 has an unanswered call before a retry, day 14 is the featured anomaly — sentiment drops noticeably and response latency roughly doubles.



\## Data schema



\- response\_latency — seconds between question and answer

\- sentiment\_score — -1 to 1, from the response transcript

\- medication\_confirmed — yes/no, morning and evening separately

\- call\_answered — yes/no



\## Team roles



\- Person A — NLP lead — branch: nlp

\- Person B — ML lead — branch: ml

\- Person C — Backend lead — branch: backend

\- Person D — Frontend lead — branch: frontend

