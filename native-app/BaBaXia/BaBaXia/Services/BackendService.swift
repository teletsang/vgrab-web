import Foundation
import SwiftUI

// MARK: - Models

enum TaskStatus: String, Codable {
    case downloading, transcribing, analyzing, recording, organizing
    case stopping, done, error
    
    var label: String {
        switch self {
        case .downloading: return "下载中"
        case .transcribing: return "转录中"
        case .analyzing: return "分析中"
        case .recording: return "录制中"
        case .organizing: return "整理中"
        case .stopping: return "停止中"
        case .done: return "完成"
        case .error: return "失败"
        }
    }
    
    var color: Color {
        switch self {
        case .downloading, .transcribing, .analyzing, .recording, .organizing: return .blue
        case .stopping: return .orange
        case .done: return .green
        case .error: return .red
        }
    }
}

struct DownloadTask: Identifiable, Codable {
    let id: String
    var title: String
    var status: TaskStatus
    var progress: Double
    var progressText: String
    var files: [DownloadFile]?
    
    enum CodingKeys: String, CodingKey {
        case id, title, status, progress
        case progressText = "progress_text"
        case files
    }
    
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? "下载中..."
        let statusStr = try c.decodeIfPresent(String.self, forKey: .status) ?? "downloading"
        status = TaskStatus(rawValue: statusStr) ?? .downloading
        progress = try c.decodeIfPresent(Double.self, forKey: .progress) ?? 0
        progressText = try c.decodeIfPresent(String.self, forKey: .progressText) ?? ""
        files = try c.decodeIfPresent([DownloadFile].self, forKey: .files)
    }
    
    init(id: String, title: String, status: TaskStatus, progress: Double, progressText: String, files: [DownloadFile]? = nil) {
        self.id = id; self.title = title; self.status = status
        self.progress = progress; self.progressText = progressText; self.files = files
    }
}

struct DownloadFile: Identifiable, Codable {
    var id: String { name }
    let name: String
    let size: Int?
    let path: String?
}

struct AnalyzeTask: Identifiable {
    let id: String
    var video: String
    var status: TaskStatus
    var progress: String
    var slicesTotal: Int
    var slicesDone: Int
    var result: String
    var reportPath: String?
}

struct TranscribeTask: Identifiable {
    let id: String
    var video: String
    var status: TaskStatus
    var progress: String
    var result: String
}

struct RecordTask: Identifiable {
    let id: String
    var title: String
    var status: TaskStatus
    var progress: String
}

// MARK: - Backend Service

@MainActor
class BackendService: ObservableObject {
    @Published var isBackendRunning = false
    @Published var downloadTasks: [DownloadTask] = []
    @Published var analyzeTasks: [AnalyzeTask] = []
    @Published var transcribeTasks: [TranscribeTask] = []
    @Published var recordTasks: [RecordTask] = []
    
    private let baseURL = "http://127.0.0.1:9999"
    private var pollingTimer: Timer?
    private var backendProcess: Process?
    
    init() {
        startBackend()
        startPolling()
    }
    
    deinit {
        pollingTimer?.invalidate()
        backendProcess?.terminate()
    }
    
    // MARK: - Backend Process
    
    private func startBackend() {
        // 检查是否已在运行
        checkBackendStatus()
        if isBackendRunning { return }
        
        // 找到 app.py 路径
        let appPath = findAppPy()
        guard !appPath.isEmpty else { return }
        
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [appPath, "--port", "9999"]
        process.currentDirectoryURL = URL(fileURLWithPath: appPath).deletingLastPathComponent()
        
        // 设置环境变量
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + (env["PATH"] ?? "")
        process.environment = env
        
        do {
            try process.run()
            backendProcess = process
            // 等待启动
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in
                self?.checkBackendStatus()
            }
        } catch {
            print("Failed to start backend: \(error)")
        }
    }
    
    private func findAppPy() -> String {
        // 优先查找同级目录
        let candidates = [
            Bundle.main.bundlePath + "/../Resources/vgrab-web/app.py",
            NSHomeDirectory() + "/vgrab-web/app.py",
            NSHomeDirectory() + "/.openclaw/workspace/openclaw-knowledge-vault/scripts/vgrab-web/app.py",
        ]
        return candidates.first { FileManager.default.fileExists(atPath: $0) } ?? ""
    }
    
    private func checkBackendStatus() {
        Task {
            do {
                let (_, resp) = try await URLSession.shared.data(from: URL(string: "\(baseURL)/api/status")!)
                isBackendRunning = (resp as? HTTPURLResponse)?.statusCode == 200
            } catch {
                isBackendRunning = false
            }
        }
    }
    
    // MARK: - Polling
    
    private func startPolling() {
        pollingTimer = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.pollTasks()
            }
        }
    }
    
    private func pollTasks() async {
        await pollDownloads()
        await pollAnalyze()
        await pollTranscribe()
        await pollRecord()
    }
    
    // MARK: - Downloads
    
    func startDownload(url: String, audioOnly: Bool, subs: Bool) {
        Task {
            let body: [String: Any] = ["url": url, "audio_only": audioOnly, "subs": subs,
                                        "proxy": UserDefaults.standard.string(forKey: "proxy") ?? ""]
            guard let data = try? await post("/api/download", body: body),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let taskId = json["task_id"] as? String else { return }
            
            downloadTasks.insert(DownloadTask(id: taskId, title: "下载中...", status: .downloading, progress: 0, progressText: ""), at: 0)
        }
    }
    
    private func pollDownloads() async {
        for i in downloadTasks.indices where downloadTasks[i].status == .downloading {
            let id = downloadTasks[i].id
            guard let data = try? await get("/api/task/\(id)"),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            
            downloadTasks[i].title = json["title"] as? String ?? downloadTasks[i].title
            downloadTasks[i].progress = json["progress"] as? Double ?? 0
            downloadTasks[i].progressText = json["progress_text"] as? String ?? ""
            if let s = json["status"] as? String { downloadTasks[i].status = TaskStatus(rawValue: s) ?? .downloading }
        }
    }
    
    // MARK: - Analyze
    
    func startAnalyze(videoPath: String, mode: String) {
        Task {
            let settings = getSettings()
            var s = settings
            s["mode"] = mode
            let body: [String: Any] = ["video_path": videoPath, "settings": s]
            guard let data = try? await post("/api/analyze", body: body),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let id = json["analyze_id"] as? String else { return }
            
            analyzeTasks.insert(AnalyzeTask(id: id, video: URL(fileURLWithPath: videoPath).lastPathComponent, status: .analyzing, progress: "准备中...", slicesTotal: 0, slicesDone: 0, result: ""), at: 0)
        }
    }
    
    private func pollAnalyze() async {
        for i in analyzeTasks.indices where analyzeTasks[i].status == .analyzing {
            let id = analyzeTasks[i].id
            guard let data = try? await get("/api/analyze/\(id)"),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            
            analyzeTasks[i].progress = json["progress"] as? String ?? ""
            analyzeTasks[i].slicesTotal = json["slices_total"] as? Int ?? 0
            analyzeTasks[i].slicesDone = json["slices_done"] as? Int ?? 0
            analyzeTasks[i].result = json["result"] as? String ?? ""
            analyzeTasks[i].reportPath = json["report_path"] as? String
            if let s = json["status"] as? String { analyzeTasks[i].status = TaskStatus(rawValue: s) ?? .analyzing }
        }
    }
    
    // MARK: - Transcribe
    
    func startTranscribe(videoPath: String) {
        Task {
            let body: [String: Any] = ["video_path": videoPath, "settings": getSettings()]
            guard let data = try? await post("/api/transcribe", body: body),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let id = json["transcribe_id"] as? String else { return }
            
            transcribeTasks.insert(TranscribeTask(id: id, video: URL(fileURLWithPath: videoPath).lastPathComponent, status: .transcribing, progress: "转录中...", result: ""), at: 0)
        }
    }
    
    private func pollTranscribe() async {
        for i in transcribeTasks.indices where transcribeTasks[i].status == .transcribing {
            let id = transcribeTasks[i].id
            guard let data = try? await get("/api/transcribe/\(id)"),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            
            transcribeTasks[i].progress = json["progress"] as? String ?? ""
            transcribeTasks[i].result = json["result"] as? String ?? ""
            if let s = json["status"] as? String { transcribeTasks[i].status = TaskStatus(rawValue: s) ?? .transcribing }
        }
    }
    
    // MARK: - Record
    
    func startRecord(url: String, title: String, maxDuration: String) {
        Task {
            var settings = getSettings()
            if !title.isEmpty { settings["title"] = title }
            if !maxDuration.isEmpty { settings["max_duration"] = maxDuration }
            let body: [String: Any] = ["stream_url": url, "settings": settings]
            guard let data = try? await post("/api/record", body: body),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let id = json["live_id"] as? String else { return }
            
            recordTasks.insert(RecordTask(id: id, title: title.isEmpty ? "直播录制" : title, status: .recording, progress: "录制中..."), at: 0)
        }
    }
    
    private func pollRecord() async {
        for i in recordTasks.indices where recordTasks[i].status == .recording {
            let id = recordTasks[i].id
            guard let data = try? await get("/api/record/\(id)"),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            
            recordTasks[i].progress = json["progress"] as? String ?? ""
            if let s = json["status"] as? String { recordTasks[i].status = TaskStatus(rawValue: s) ?? .recording }
        }
    }
    
    // MARK: - Helpers
    
    private func getSettings() -> [String: Any] {
        let ud = UserDefaults.standard
        return [
            "llm_url": ud.string(forKey: "llmUrl") ?? "http://127.0.0.1:8080",
            "model": ud.string(forKey: "llmModel") ?? "gemma-4",
            "api_key": ud.string(forKey: "apiKey") ?? "",
            "frame_interval": Int(ud.string(forKey: "frameInterval") ?? "30") ?? 30,
            "max_tokens": Int(ud.string(forKey: "maxTokens") ?? "4096") ?? 4096,
            "temperature": Double(ud.string(forKey: "temperature") ?? "0.3") ?? 0.3,
            "proxy": ud.string(forKey: "proxy") ?? "",
            "output_dir": ud.string(forKey: "outputDir") ?? "",
        ]
    }
    
    private func get(_ path: String) async throws -> Data {
        let url = URL(string: baseURL + path)!
        let (data, _) = try await URLSession.shared.data(from: url)
        return data
    }
    
    private func post(_ path: String, body: [String: Any]) async throws -> Data {
        var request = URLRequest(url: URL(string: baseURL + path)!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await URLSession.shared.data(for: request)
        return data
    }
}
