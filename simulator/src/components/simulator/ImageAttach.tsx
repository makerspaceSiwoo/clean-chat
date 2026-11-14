"use client";
/**
 * 이미지 첨부 칸 (OCR 처럼 입력에 이미지 경로가 있는 모듈).
 * 실행하면 이미지를 로컬 모듈 서버로 보내고, 서버가 저장한 경로로 실제 모듈 함수를 부른다.
 */
import { useState } from "react";
import { formatBytes, IMAGE_TYPES } from "@/lib/image";

export interface AttachedImage {
  name: string;
  size: number;
  /** 미리보기용 blob URL (브라우저 안에서만 유효) */
  url: string;
  /** 실행할 때 서버로 보낼 원본 파일 */
  file: File;
}

interface Props {
  field: string;
  image: AttachedImage | null;
  error?: string;
  onAttach: (file: File) => void;
  onClear: () => void;
}

export function ImageAttach({ field, image, error, onAttach, onClear }: Props) {
  const [dragging, setDragging] = useState(false);
  const pick = (files: FileList | null) => {
    const file = files?.[0];
    if (file) onAttach(file);
  };

  return (
    <div className="mt-3">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-slate-600" htmlFor="image-attach">
          이미지 첨부
        </label>
        {image && (
          <button type="button" onClick={onClear} className="text-xs text-slate-600 underline-offset-2 hover:underline">
            첨부 빼기
          </button>
        )}
      </div>
      <div
        data-testid="image-drop"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          pick(e.dataTransfer.files);
        }}
        className={`mt-1 rounded-md border border-dashed p-2 ${dragging ? "border-sky-500 bg-sky-50" : "border-slate-300"}`}
      >
        <input
          id="image-attach"
          type="file"
          accept={IMAGE_TYPES.join(",")}
          onChange={(e) => {
            pick(e.target.files);
            e.target.value = ""; // 같은 파일을 다시 골라도 반응하게
          }}
          className="block w-full text-xs text-slate-600 file:mr-2 file:rounded file:border-0 file:bg-slate-100 file:px-2 file:py-1 file:text-xs"
        />
        {image ? (
          <figure className="mt-2">
            {/* eslint-disable-next-line @next/next/no-img-element -- blob URL 미리보기라 next/image 를 쓸 수 없음 */}
            <img src={image.url} alt={`첨부한 이미지: ${image.name}`} className="max-h-40 w-full rounded border border-slate-200 object-contain" />
            <figcaption className="mt-1 font-mono text-[11px] text-slate-500">
              {image.name} · {formatBytes(image.size)}
            </figcaption>
          </figure>
        ) : (
          <p className="mt-1 text-[11px] text-slate-500">파일을 고르거나 여기로 끌어다 놓으세요 (PNG·JPG·WEBP·BMP, 10MB 이하)</p>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {error}
        </p>
      )}
      <p className="mt-1 text-[11px] text-slate-500">
        실행하면 이미지를 로컬 모듈 서버로 보냅니다. 서버가 <code>.clean-chat/uploads/</code> 에 저장하고 입력의 <code>{field}</code> 를 그 경로로 바꿉니다.
      </p>
    </div>
  );
}
