import SwiftUI

struct TranscribeView: View {
    @EnvironmentObject var backend: BackendService
    @State private var videoPath = ""
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            GroupBox {
                HStack {
                    TextField("视频文件路径", text: $videoPath)
                        .textFieldStyle(.roundedBorder)
                    
                    Button(action: browseFile) {
                        Image(systemName: "folder")
                    }
                    
                    Button("转录") { startTranscribe() }
                        .buttonStyle(.borderedProminent)
                        .disabled(videoPath.isEmpty)
                }
                
                Text("Whisper 语音转文字，适合访谈/教程/演讲类视频")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            
            if !backend.transcribeTasks.isEmpty {
                List {
                    ForEach(backend.transcribeTasks) { task in
                        TranscribeTaskRow(task: task)
                    }
                }
                .listStyle(.inset(alternatesRowBackgrounds: true))
            } else {
                Spacer()
                HStack {
                    Spacer()
                    VStack(spacing: 8) {
                        Image(systemName: "waveform")
                            .font(.system(size: 40))
                            .foregroundStyle(.tertiary)
                        Text("选择视频开始转录")
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
        panel.allowedContentTypes = [.movie, .mpeg4Movie, .quickTimeMovie, .avi, .audio, .mp3]
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            videoPath = url.path
        }
    }
    
    private func startTranscribe() {
        guard !videoPath.isEmpty else { return }
        backend.startTranscribe(videoPath: videoPath)
    }
}

struct TranscribeTaskRow: View {
    let task: TranscribeTask
    
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(task.video)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                StatusBadge(status: task.status)
            }
            
            ProgressView(value: task.status == .done ? 1.0 : 0.5)
                .progressViewStyle(.linear)
            
            Text(task.progress)
                .font(.caption)
                .foregroundStyle(.secondary)
            
            if !task.result.isEmpty {
                DisclosureGroup("查看转录") {
                    ScrollView {
                        Text(task.result)
                            .font(.callout)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(maxHeight: 300)
                }
            }
        }
        .padding(.vertical, 4)
    }
}
