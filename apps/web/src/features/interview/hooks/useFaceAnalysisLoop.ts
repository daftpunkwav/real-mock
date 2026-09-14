"use client";

import { useCallback, useEffect, useRef } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import { getTranslator } from "@/i18n/resolve";
import type { FaceAnalysis as BaseFaceAnalysis } from "@/types";

/** Face analysis snapshot reported to the room. */
export interface FaceAnalysis extends BaseFaceAnalysis {
  face_detected: boolean;
  looking_away: boolean;
  nervousness: number;
  face_count: number;
}

interface DetectedFace {
  boundingBox: { x: number; y: number; width: number; height: number };
}

interface BrowserFaceDetector {
  detect(source: HTMLVideoElement): Promise<DetectedFace[]>;
}

interface FaceDetectorOptions {
  fastMode?: boolean;
  maxDetectedFaces?: number;
}

declare global {
  interface Window {
    FaceDetector: new (options?: FaceDetectorOptions) => BrowserFaceDetector;
  }
}

interface UseFaceAnalysisLoopOptions {
  videoRef: RefObject<HTMLVideoElement | null>;
  cameraOn: boolean;
  enabled: boolean;
  onFaceAnalysis?: (analysis: FaceAnalysis) => void;
  setFaceStatus: Dispatch<SetStateAction<string>>;
}

/**
 * Poll FaceDetector every 3s; looking_away at offset over 0.35, nervousness from jitter variance.
 */
export function useFaceAnalysisLoop({
  videoRef,
  cameraOn,
  enabled,
  onFaceAnalysis,
  setFaceStatus,
}: UseFaceAnalysisLoopOptions) {
  const faceDetectorRef = useRef<BrowserFaceDetector | null>(null);
  const jitterHistory = useRef<number[]>([]);
  // Report a missing FaceDetector API only once.
  const detectorUnavailableReportedRef = useRef(false);

  // Recreate the detector when the camera turns on.
  useEffect(() => {
    if (!cameraOn) {
      faceDetectorRef.current = null;
      return;
    }
    detectorUnavailableReportedRef.current = false;
    if ("FaceDetector" in window) {
      try {
        faceDetectorRef.current = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 1 });
      } catch {
        faceDetectorRef.current = null;
      }
    }
    return () => {
      faceDetectorRef.current = null;
    };
  }, [cameraOn]);

  const analyzeFace = useCallback(async () => {
    const video = videoRef.current;
    if (!video || !cameraOn || video.readyState < 2) return;

    const analysis: FaceAnalysis = {
      face_detected: false,
      looking_away: true,
      nervousness: 0,
      face_count: 0,
    };

    if (faceDetectorRef.current) {
      try {
        const faces = await faceDetectorRef.current.detect(video);
        analysis.face_count = faces.length;
        analysis.face_detected = faces.length > 0;

        if (faces.length > 0) {
          const face = faces[0]?.boundingBox;
          if (face) {
            const cx = face.x + face.width / 2;
            const cy = face.y + face.height / 2;
            const vcx = video.videoWidth / 2;
            const vcy = video.videoHeight / 2;
            const offset = Math.hypot(cx - vcx, cy - vcy) / Math.hypot(vcx, vcy);
            // Flag looking_away when the face offset exceeds 0.35.
            analysis.looking_away = offset > 0.35;
            // Keep the last 8 offsets as the jitter window.
            jitterHistory.current.push(offset);
            if (jitterHistory.current.length > 8) jitterHistory.current.shift();
            // Score nervousness once at least 3 samples exist.
            if (jitterHistory.current.length >= 3) {
              const avg =
                jitterHistory.current.reduce((a, b) => a + b, 0) /
                jitterHistory.current.length;
              const variance =
                jitterHistory.current.reduce((s, v) => s + (v - avg) ** 2, 0) /
                jitterHistory.current.length;
              // Scale jitter variance by 20, clamped to 1.
              analysis.nervousness = Math.min(1, variance * 20);
            }
          } else {
            jitterHistory.current.push(0);
            if (jitterHistory.current.length > 8) jitterHistory.current.shift();
          }
          setFaceStatus(
            analysis.looking_away
              ? getTranslator("interview")("video.face.lookingAway")
              : analysis.nervousness > 0.5
                ? getTranslator("interview")("video.face.nervous")
                : getTranslator("interview")("video.face.normal"),
          );
        } else {
          setFaceStatus(getTranslator("interview")("video.face.none"));
        }
      } catch {
        setFaceStatus(getTranslator("interview")("video.face.unavailable"));
      }
      onFaceAnalysis?.(analysis);
    } else {
      // No detector: emit a negative result only once.
      if (!detectorUnavailableReportedRef.current) {
        detectorUnavailableReportedRef.current = true;
        setFaceStatus(getTranslator("interview")("video.face.noDetectorApi"));
        onFaceAnalysis?.(analysis); // Report face_detected false.
      }
    }
  }, [cameraOn, onFaceAnalysis, videoRef, setFaceStatus]);

  useEffect(() => {
    if (!cameraOn || !enabled) return;
    // Poll face analysis every 3s while the camera is on.
    const interval = setInterval(() => {
      analyzeFace();
    }, 3000);
    return () => clearInterval(interval);
  }, [cameraOn, enabled, analyzeFace]);

  return {};
}
