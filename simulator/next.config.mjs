/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 레포 루트에도 lock 파일(uv.lock)이 있어 Next 가 작업 폴더를 헷갈리지 않게 고정
  outputFileTracingRoot: new URL(".", import.meta.url).pathname,
};

export default nextConfig;
