import SwiftUI

struct AnalyzeView: View {
    @EnvironmentObject var backend: BackendService
    @State private var videoPath = ""
    @State private var analyzeMode = "summary"
    
    let modes = [
        ("summary", "内容总结"),
        ("visual", "视觉风格"),
        ("tutorial", "教程拆解"),
        ("creative", "创意分析"),
    ]
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            GroupBox {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        TextField("视频文件路径", text: $videoPath)
                            .textFieldStyle(.roundedBorder)
                        
                        Button(action: browseFile) {
                            Image(systemName: "folder")
                        }
                        
                        Button("分析") { startAnalyze() }
                            .buttonStyle(.borderedProminent)
                            .disabled(videoPath.isEmpty)
                    }
                    
                    Picker("分析模式", selection: $analyzeMode) {
                        ForEach(modes, id: \.0) { mode in
                            Text(mode.1).tag(mode.0)
                        }
                    }
                    .pickerStyle(.segmented)
                }
            }
            
            // 任务列表
            if !backend.analyzeTasks.isEmpty {
                List {
                    ForEach(backend.analyzeTasks) { task in
                        AnalyzeTaskRow(task: task)
                    }
                }
                .listStyle(.inset(alternatesRowBackgrounds: true))
            } else {
                Spacer()
                HStack {
                    Spacer()
                    VStack(spacing: 8) {
                        Image(systemName: "eye")
                            .font(.system(size: 40))
                            .foregroundStyle(.tertiary)
                        Text("选择视频开始分析")
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                Spacer()
            }
        }
        .padding()
    }
    
    private func browseFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.movie, .mpeg4Movie, .quickTimeMovie, .avi]
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            videoPath = url.path
        }
    }
    
    private func startAnalyze() {
        guard !videoPath.isEmpty else { return }
        backend.startAnalyze(videoPath: videoPath, mode: analyzeMode)
    }
}

struct AnalyzeTaskRow: View {
    let task: AnalyzeTask
    
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(task.video)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                StatusBadge(status: task.status)
            }
            
            ProgressView(value: Double(task.slicesDone), total: Double(max(task.slicesTotal, 1)))
                .progressViewStyle(.linear)
            
            Text(task.progress)
                .font(.caption)
                .foregroundStyle(.secondary)
            
            if !task.result.isEmpty {
                DisclosureGroup("查看报告") {
                    ScrollView {
                        Text(task.result)
                            .font(.callout)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(maxHeight: 300)
                }
                
                if let reportPath = task.reportPath {
                    HStack {
                        Image(systemName: "doc.text.fill")
                            .foregroundStyle(.green)
                        Text(reportPath)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Button("打开") {
                            NSWorkspace.shared.selectFile(reportPath, inFileViewerRootedAtPath: "")
                        }
                        .font(.caption)
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}
