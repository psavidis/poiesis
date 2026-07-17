# Poiesis

Poiesis (ποίησις) is an AI-powered content creation pipeline that transforms raw footage into polished, publish-ready videos.

Built as an autonomous, agent-driven system, Poiesis orchestrates the entire production workflow—from ingesting recordings and generating transcripts to scripting, editing, rendering, and preparing content for publication. Its goal is to eliminate repetitive manual work while keeping creators in control of the creative process.

# Vision

Creating high-quality videos should be a creative task, not an editing marathon. Poiesis automates the production pipeline so creators can focus on ideas instead of repetitive workflows.

# Python Library Dependencies

- pip install json-repair



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