import SwiftUI

struct DownloadView: View {
    @EnvironmentObject var backend: BackendService
    @State private var url = ""
    @State private var audioOnly = false
    @State private var downloadSubs = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // 输入区
            GroupBox {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        TextField("粘贴视频链接...", text: $url)
                            .textFieldStyle(.roundedBorder)
                            .onSubmit { startDownload() }
                        
                        Button("下载") { startDownload() }
                            .buttonStyle(.borderedProminent)
                            .disabled(url.isEmpty)
                    }
                    
                    HStack(spacing: 20) {
                        Toggle("仅音频", isOn: $audioOnly)
                            .toggleStyle(.switch)
                        Toggle("字幕", isOn: $downloadSubs)
                            .toggleStyle(.switch)
                    }
                    .font(.callout)
                }
            }
            
            // 任务列表
            if !backend.downloadTasks.isEmpty {
                List {
                    ForEach(backend.downloadTasks) { task in
                        DownloadTaskRow(task: task)
                    }
                }
                .listStyle(.inset(alternatesRowBackgrounds: true))
            } else {
                Spacer()
                HStack {
                    Spacer()
                    VStack(spacing: 8) {
                        Image(systemName: "arrow.down.circle")
                            .font(.system(size: 40))
                            .foregroundStyle(.tertiary)
                        Text("粘贴链接开始下载")
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                Spacer()
            }
        }
        .padding()
    }
    
    private func startDownload() {
        guard !url.isEmpty else { return }
        backend.startDownload(url: url, audioOnly: audioOnly, subs: downloadSubs)
        url = ""
    }
}

struct DownloadTaskRow: View {
    let task: DownloadTask
    
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(task.title)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                StatusBadge(status: task.status)
            }
            
            if task.status == .downloading {
                ProgressView(value: task.progress, total: 100)
                    .progressViewStyle(.linear)
            }
            
            Text(task.progressText)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}

struct StatusBadge: View {
    let status: TaskStatus
    
    var body: some View {
        Text(status.label)
            .font(.caption2.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(status.color.opacity(0.15))
            .foregroundStyle(status.color)
            .clipShape(Capsule())
    }
}
