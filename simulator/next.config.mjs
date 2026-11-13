import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 레포 루트에도 lock 파일(uv.lock)이 있어 Next 가 작업 폴더를 헷갈리지 않게 고정.
  // URL.pathname 대신 fileURLToPath: Windows 경로(C:\...)와 한글·공백이 든 경로에서도 올바른 폴더가 된다.
  outputFileTracingRoot: dirname(fileURLToPath(import.meta.url)),
};

export default nextConfig;
