// 本地 OCR：macOS Vision framework。中文(zh-Hans)+英文，离线，免费。
// 用法: ocr <图片路径...>   输出以 ---FILE---<path> 分隔
import Foundation
import Vision
import AppKit

setvbuf(stdout, nil, _IOFBF, 1 << 20)

for path in CommandLine.arguments.dropFirst() {
    print("---FILE---\(path)")
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("__ERR__ cannot load")
        continue
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hans", "en-US"]
    req.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do {
        try handler.perform([req])
    } catch {
        print("__ERR__ \(error.localizedDescription)")
        continue
    }
    let obs = req.results ?? []
    // 按纵向位置排序，保证阅读顺序（Vision 返回顺序不保证）
    let sorted = obs.sorted { $0.boundingBox.maxY > $1.boundingBox.maxY }
    for o in sorted {
        if let c = o.topCandidates(1).first, c.confidence > 0.3 {
            print(c.string)
        }
    }
}
