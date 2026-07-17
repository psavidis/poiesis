



# Pipeline Order

1. original_footage

2. prepare_footage.py 
   - Produces processing/manifest.json
3. transcribe_footage.sh ✅ 
   - processing/transcripts/
4. normalize_transcripts.py
   - processing/segments/
5. analyze_segments.py (Ollama) ← later

## 1. Transcribe Original Footage

Execute the script against the project root which contains a folder `original_footage`.
The output of the script will produce a folder `processing/transcripts` containing the transcriptions of the original footage.

**Example usage**:
```bash
./transcribe_footage.sh /path/to/project
```

# 2. 