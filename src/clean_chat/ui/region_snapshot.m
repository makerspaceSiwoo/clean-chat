// 오버레이 아래 영역만 메모리로 복사한다. 호출자는 단일 백그라운드 작업자다.
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreVideo/CoreVideo.h>
#import <unistd.h>

static int fail(char *error, size_t capacity, NSString *message) {
    snprintf(error, capacity, "%s", message.UTF8String ?: "화면 이미지를 가져오지 못했습니다.");
    return 0;
}

int cc_snapshot(double x, double y, double w, double h, int width, int height,
                unsigned char *output, char *error, size_t capacity) {
    @autoreleasepool {
        if (@available(macOS 14.0, *)) {
            CGRect region = CGRectMake(x, y, w, h);
            CGDirectDisplayID displays[16];
            uint32_t count = 0;
            CGDirectDisplayID displayID = 0;
            CGGetDisplaysWithRect(region, 16, displays, &count);
            for (uint32_t i = 0; i < count; ++i) {
                if (CGRectContainsRect(CGDisplayBounds(displays[i]), region)) {
                    displayID = displays[i];
                    break;
                }
            }
            if (!displayID)
                return fail(error, capacity, @"오버레이 전체를 한 모니터 안으로 옮겨 주세요.");

            static SCContentFilter *filter;
            static CGDirectDisplayID cachedDisplay;
            if (!filter || displayID != cachedDisplay) {
                dispatch_semaphore_t ready = dispatch_semaphore_create(0);
                __block SCShareableContent *content;
                __block NSError *problem;
                [SCShareableContent getShareableContentExcludingDesktopWindows:NO onScreenWindowsOnly:YES
                    completionHandler:^(SCShareableContent *value, NSError *err) {
                        content = value;
                        problem = err;
                        dispatch_semaphore_signal(ready);
                    }];
                if (dispatch_semaphore_wait(ready, dispatch_time(DISPATCH_TIME_NOW, 3*NSEC_PER_SEC)))
                    return fail(error, capacity, @"화면 목록 응답 대기 중");
                if (!content) return fail(error, capacity, problem.localizedDescription);
                SCRunningApplication *ownApp = nil;
                SCDisplay *display = nil;
                for (SCRunningApplication *app in content.applications)
                    if (app.processID == getpid()) ownApp = app;
                for (SCDisplay *candidate in content.displays)
                    if (candidate.displayID == displayID) display = candidate;
                if (!ownApp || !display)
                    return fail(error, capacity, @"오버레이 창과 모니터를 확인하는 중");
                filter = [[SCContentFilter alloc] initWithDisplay:display excludingApplications:@[ownApp] exceptingWindows:@[]];
                cachedDisplay = displayID;
            }

            CGRect bounds = CGDisplayBounds(displayID);
            SCStreamConfiguration *config = [SCStreamConfiguration new];
            config.sourceRect = CGRectOffset(region, -bounds.origin.x, -bounds.origin.y);
            config.width = width;
            config.height = height;
            config.pixelFormat = kCVPixelFormatType_32BGRA;
            config.showsCursor = NO;
            config.capturesAudio = NO;
            if (@available(macOS 15.0, *)) config.captureMicrophone = NO;

            dispatch_semaphore_t done = dispatch_semaphore_create(0);
            __block id retainedSample;
            __block NSError *problem;
            [SCScreenshotManager captureSampleBufferWithFilter:filter configuration:config
                completionHandler:^(CMSampleBufferRef buffer, NSError *err) {
                    retainedSample = (__bridge id)buffer;
                    problem = err;
                    dispatch_semaphore_signal(done);
                }];
            if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 3*NSEC_PER_SEC)))
                return fail(error, capacity, @"화면 이미지 응답 대기 중");
            if (!retainedSample) {
                filter = nil;
                return fail(error, capacity, problem.localizedDescription);
            }
            CVPixelBufferRef pixels = CMSampleBufferGetImageBuffer((__bridge CMSampleBufferRef)retainedSample);
            if (!pixels || CVPixelBufferGetPixelFormatType(pixels) != kCVPixelFormatType_32BGRA ||
                CVPixelBufferGetWidth(pixels) != width || CVPixelBufferGetHeight(pixels) != height ||
                CVPixelBufferLockBaseAddress(pixels, kCVPixelBufferLock_ReadOnly) != kCVReturnSuccess)
                return fail(error, capacity, @"화면 이미지 형식을 확인할 수 없습니다.");
            const uint8_t *base = CVPixelBufferGetBaseAddress(pixels);
            size_t stride = CVPixelBufferGetBytesPerRow(pixels);
            for (int row = 0; row < height; ++row)
                memcpy(output + (size_t)row * width * 4, base + row * stride, width * 4);
            CVPixelBufferUnlockBaseAddress(pixels, kCVPixelBufferLock_ReadOnly);
            // ARC가 픽셀 복사 전에 샘플의 수명을 끝내지 않도록 한다.
            (void)CFGetTypeID((__bridge CFTypeRef)retainedSample);
            return 1;
        }
        return fail(error, capacity, @"영역 미리보기에는 macOS 14 이상이 필요합니다.");
    }
}
