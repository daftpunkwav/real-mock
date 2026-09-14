"use client";

import { useCallback, useRef, useState } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import { getTranslator } from "@/i18n/resolve";

/**
 * Owns the getUserMedia lifecycle: start, stop, toggle, concurrency prevention,
 * and disposal of old tracks. Frame analysis and audio recording belong to
 * useFaceAnalysisLoop and useAudioRecorder.
 * @param videoRef Video element that receives the acquired stream.
 * @param setFaceStatus Updates camera-related status copy in the parent component.
 */
export function useCameraStream(
  videoRef: RefObject<HTMLVideoElement | null>,
  setFaceStatus: Dispatch<SetStateAction<string>>,
) {
  const [cameraOn, setCameraOn] = useState(false);
  const streamRef = useRef<MediaStream | null>(null);
  const acquiringRef = useRef(false);

  const startCamera = useCallback(async () => {
    if (acquiringRef.current) return;
    acquiringRef.current = true;
    try {
      // Stop the old stream before acquiring another one to avoid leaking tracks.
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      if (!acquiringRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setCameraOn(true);
    } catch {
      setFaceStatus(getTranslator("interview")("video.camera.permissionDenied"));
    } finally {
      acquiringRef.current = false;
    }
  }, [videoRef, setFaceStatus]);

  const stopCamera = useCallback(() => {
    acquiringRef.current = false;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraOn(false);
    setFaceStatus(getTranslator("interview")("video.face.initial"));
  }, [videoRef, setFaceStatus]);

  const toggleCamera = useCallback(() => {
    if (cameraOn) stopCamera();
    else void startCamera();
  }, [cameraOn, startCamera, stopCamera]);

  return { cameraOn, startCamera, stopCamera, toggleCamera };
}
