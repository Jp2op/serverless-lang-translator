import React, { useState, useRef } from "react";
import { createFFmpeg, fetchFile } from '@ffmpeg/ffmpeg';

const ffmpeg = createFFmpeg({
  log: true,
  corePath: '/ffmpeg/ffmpeg-core.js',
});


export default function AudioTranslator() {
  const [file, setFile] = useState(null);
  const [transcription, setTranscription] = useState("");
  const [translatedAudioUrl, setTranslatedAudioUrl] = useState(null);
  const [translatedText, setTranslatedText] = useState("");
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [responseFormat, setResponseFormat] = useState(null);
  const [codecSupported, setCodecSupported] = useState(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioPlayerRef = useRef(null);

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setTranscription("");
    setTranslatedAudioUrl(null);
    setTranslatedText("");
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsLoading(true);
    setTranscription("Processing your audio...");
    const formData = new FormData();
    formData.append("file", file);

    try {
      const uploadRes = await fetch(
        "https://g5h6md1c6e.execute-api.us-east-1.amazonaws.com/dev/upload",
        {
          method: "POST",
          body: formData,
        }
      );
      const uploadData = await uploadRes.json();

      if (!uploadData.file_key) {
        throw new Error("No file key received from upload");
      }

      // Poll for translation results
      let attempts = 0;
      const maxAttempts = 30;

      while (attempts < maxAttempts) {
        try {
          // Remove the `.mp3` extension from the file_key
          const fileKeyWithoutExtension = uploadData.file_key.replace(/\.mp3$/, "");

          const checkRes = await fetch(
            `https://omdw06wgtj.execute-api.us-east-1.amazonaws.com/Dev/status/${fileKeyWithoutExtension}_output.json`,
            {
              method: "GET",
              headers: {
                "Accept": "*/*", // Matches the Postman "Accept" header
                "Cache-Control": "no-cache", // Matches the Postman "Cache-Control" header
                "User-Agent": "PostmanRuntime/7.43.3", // Optional: Mimic Postman user agent
                "Accept-Encoding": "gzip, deflate, br", // Matches the Postman "Accept-Encoding" header
                "Connection": "keep-alive", // Matches the Postman "Connection" header
              },
            }
          );

          if (!checkRes.ok) {
            console.error(`Fetch failed with status: ${checkRes.status}`);
            throw new Error("Failed to fetch translation status");
          }

          const checkData = await checkRes.json();

          if (checkData.status === "complete") {
            setResponseFormat(checkData.format); // 'audio_only' or 'audio_text'

            if (checkData.format === "audio_text") {
              setTranscription(checkData.transcriptionText || "");
              setTranslatedText(checkData.translatedText || "");
            }

            if (checkData.translatedAudioUrl) {
              setTranslatedAudioUrl(checkData.translatedAudioUrl);
            }

            setIsLoading(false);
            return; // Exit the loop if the status is "completed"
          }
        } catch (error) {
          console.error("Error during polling:", error);
        }

        // Wait for 2 seconds before the next attempt
        await new Promise((resolve) => setTimeout(resolve, 2000));
        attempts++;
      }

      // If the loop exits without completing, show a timeout message
      setIsLoading(false);
      setTranscription("Translation timed out. Please try again.");
    } catch (error) {
      console.error("Error:", error);
      setIsLoading(false);
      setTranscription("Error processing audio.");
    }
  };

  const convertToMp3 = async (audioData) => {
    if (!ffmpeg.isLoaded()) {
      await ffmpeg.load();
    }

    // Load the audio file into ffmpeg
    ffmpeg.FS('writeFile', 'input.wav', await fetchFile(audioData));

    // Run the ffmpeg command to convert WAV to MP3
    await ffmpeg.run('-i', 'input.wav', '-b:a', '128k', 'output.mp3');

    // Retrieve the converted MP3 file
    const mp3Data = ffmpeg.FS('readFile', 'output.mp3');

    // Create a Blob and File object for the MP3
    const mp3Blob = new Blob([mp3Data.buffer], { type: 'audio/mp3' });
    return new File([mp3Blob], 'converted_audio.mp3', { type: 'audio/mp3' });
  };

  const checkMp3Support = async () => {
    const types = ["audio/mp3", "audio/mpeg", "audio/webm;codecs=mp3"];

    for (const type of types) {
      if (MediaRecorder.isTypeSupported(type)) {
        return type;
      }
    }
    return null;
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const supportedType = await checkMp3Support();
      setCodecSupported(supportedType);

      const mediaRecorder = new window.MediaRecorder(stream, {
        mimeType: supportedType || "audio/webm",
        audioBitsPerSecond: 128000,
      });

      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) =>
        audioChunksRef.current.push(e.data);
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, {
          type: codecSupported || 'audio/webm',
        });

        // Convert the audio to MP3 using ffmpeg.js
        const finalFile = await convertToMp3(audioBlob);

        setFile(finalFile);
        setTranscription('');
        setTranslatedAudioUrl(null);
        setTranslatedText('');
      };

      mediaRecorder.start(1000); // Collect data every second
      setRecording(true);
    } catch (error) {
      console.error("Recording failed:", error);
      alert(
        "Could not start recording. Please check your microphone permissions."
      );
    }
  };

  const recordAndTranscribe = async () => {
    if (recording) {
      setProcessing(true);
      try {
        mediaRecorderRef.current.stop();
        setRecording(false);
        // Wait for the onstop event to complete
        await new Promise((resolve) => {
          mediaRecorderRef.current.onstop = async () => {
            const audioBlob = new Blob(audioChunksRef.current, {
              type: codecSupported || "audio/webm",
            });

            const finalFile = codecSupported
              ? new File([audioBlob], "recorded_audio.mp3", {
                  type: "audio/mp3",
                })
              : await convertToMp3(audioBlob);

            setFile(finalFile);
            resolve();
          };
        });
        await handleUpload();
      } catch (error) {
        console.error("Error processing recording:", error);
        alert("Error processing the recording. Please try again.");
      } finally {
        setProcessing(false);
      }
    } else {
      startRecording();
    }
  };

  return (
    <div
      style={{
        maxWidth: 800,
        margin: "40px auto",
        padding: 32,
        background: "linear-gradient(145deg, #ffffff, #f0f0f0)",
        borderRadius: 20,
        boxShadow: "20px 20px 60px #d0d0d0, -20px -20px 60px #ffffff",
      }}
    >
      <h2
        style={{
          color: "#2c3e50",
          fontSize: "28px",
          marginBottom: "24px",
          textAlign: "center",
          fontWeight: "600",
        }}
      >
        Audio Translator
      </h2>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "20px",
        }}
      >
        <div
          style={{
            padding: "20px",
            border: "2px dashed #bdc3c7",
            borderRadius: "12px",
            textAlign: "center",
            transition: "all 0.3s ease",
            cursor: "pointer",
            backgroundColor: "#f8f9fa",
          }}
        >
          <input
            type="file"
            accept="audio/*"
            onChange={handleFileChange}
            style={{
              display: "none",
            }}
            id="file-input"
          />
          <label
            htmlFor="file-input"
            style={{
              cursor: "pointer",
              color: "#7f8c8d",
              fontSize: "16px",
            }}
          >
            Drop your audio file here or click to browse
          </label>
          {file && (
            <div
              style={{
                marginTop: "8px",
                color: "#27ae60",
                fontSize: "14px",
              }}
            >
              Selected: {file.name}
            </div>
          )}
        </div>

        <div
          style={{
            display: "flex",
            gap: "12px",
            flexWrap: "wrap",
            justifyContent: "center",
          }}
        >
          <button
            onClick={recordAndTranscribe}
            style={{
              background: recording ? "#e74c3c" : "#27ae60",
              color: "#fff",
              border: "none",
              borderRadius: "30px",
              padding: "12px 24px",
              cursor: "pointer",
              opacity: processing ? 0.7 : 1,
              transition: "all 0.3s ease",
              transform: recording ? "scale(1.05)" : "scale(1)",
              fontWeight: "600",
              minWidth: "180px",
              boxShadow: "0 4px 15px rgba(0,0,0,0.1)",
            }}
            disabled={processing}
          >
            {processing
              ? "Processing..."
              : recording
              ? "Stop & Transcribe"
              : "Record & Transcribe"}
          </button>
        </div>

        {responseFormat === "audio_text" && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "20px",
              margin: "20px 0",
            }}
          >
            <div
              style={{
                padding: "20px",
                background: "#fff",
                borderRadius: "12px",
                boxShadow: "inset 0 2px 4px rgba(0,0,0,0.06)",
              }}
            >
              <h3 style={{ color: "#34495e", marginBottom: "10px" }}>
                Original Text
              </h3>
              <p style={{ color: "#2c3e50", lineHeight: "1.6" }}>
                {transcription || "Original text will appear here..."}
              </p>
            </div>

            <div
              style={{
                padding: "20px",
                background: "#fff",
                borderRadius: "12px",
                boxShadow: "inset 0 2px 4px rgba(0,0,0,0.06)",
              }}
            >
              <h3 style={{ color: "#34495e", marginBottom: "10px" }}>
                Translated Text
              </h3>
              <p style={{ color: "#2c3e50", lineHeight: "1.6" }}>
                {translatedText || "Translation will appear here..."}
              </p>
            </div>
          </div>
        )}

        {translatedAudioUrl && (
          <div
            style={{
              marginTop: "20px",
              padding: "20px",
              background: "#fff",
              borderRadius: "12px",
              boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
            }}
          >
            <h3 style={{ color: "#34495e", marginBottom: "10px" }}>
              {responseFormat === "audio_only"
                ? "Translated Audio Only"
                : "Translated Audio"}
            </h3>
            <audio
              key={translatedAudioUrl} // Force React to re-render the audio element
              ref={audioPlayerRef}
              controls
              style={{ width: "100%" }}
              src={translatedAudioUrl}
              onLoadedMetadata={(e) => console.log("Audio duration:", e.target.duration)}
              onError={(e) => console.error("Error loading audio:", e)}
            />
            <button
              onClick={() => {
                audioPlayerRef.current.load(); // Reload the audio element
                audioPlayerRef.current.play(); // Play the audio
                if (translatedAudioUrl) {
                  window.open(translatedAudioUrl, "_blank"); // Open the URL in a new tab
                }
              }}
              style={{
                marginTop: "10px",
                background: "#3498db",
                color: "#fff",
                border: "none",
                borderRadius: "8px",
                padding: "10px 20px",
                cursor: "pointer",
                fontWeight: "600",
                boxShadow: "0 4px 15px rgba(0,0,0,0.1)",
              }}
            >
              Play Translated Audio
            </button>
          </div>
        )}

        {recording && (
          <div
            style={{
              position: "fixed",
              top: "20px",
              right: "20px",
              background: "#e74c3c",
              color: "white",
              padding: "8px 16px",
              borderRadius: "20px",
              animation: "pulse 2s infinite",
              boxShadow: "0 2px 10px rgba(231, 76, 60, 0.3)",
            }}
          >
            Recording...
          </div>
        )}

        {isLoading && (
          <div
            style={{
              position: "fixed",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              background: "rgba(0,0,0,0.8)",
              color: "white",
              padding: "20px 40px",
              borderRadius: "30px",
              zIndex: 1000,
            }}
          >
            Processing...
          </div>
        )}
      </div>

      <style>
        {`
          @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
          }

          button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
          }

          button:active {
            transform: translateY(0);
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
          }
        `}
      </style>
    </div>
  );
}