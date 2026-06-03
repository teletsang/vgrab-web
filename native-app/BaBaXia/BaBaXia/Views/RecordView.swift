import SwiftUI

struct RecordView: View {
    @EnvironmentObject var backend: BackendService
    @State private var streamUrl = ""
    @State private var title = ""
    @State private var maxDuration = ""
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            GroupBox {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        TextField("粘贴 HLS/FLV 流地址 (m3u8/flv)", text: $streamUrl)
                            .textFieldStyle(.roundedBorder)
                        
                        Button("录制") { startRecord() }
                            .buttonStyle(.borderedProminent)
                            .disabled(streamUrl.isEmpty)
                    }
                    
                    HStack(spacing: 16) {
                        TextField("标题（可选）", text: $title)
                            .textFieldStyle(.roundedBorder)
                            .frame(maxWidth: 200)
                        
                        TextField("最长分钟（留空不限）", text: $maxDuration)
                            .textFieldStyle(.roundedBorder)
                            .frame(maxWidth: 160)
                    }
                    
                    Text("小红书/抖音/B站等直播，需通过浏览器 DevTools 拿到流地址")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }
            
            if !backend.recordTasks.isEmpty {
                List {
                    ForEach(backend.recordTasks) { task in
                        RecordTaskRow(task: task)
                    }
                }
                .listStyle(.inset(alternatesRowBackgrounds: true))
            } else {
                Spacer()
                HStack {
                    Spacer()
                    VStack(spacing: 8) {
                        Image(systemName: "record.circle")
                            .font(.system(size: 40))
                            .foregroundStyle(.tertiary)
                        Text("粘贴流地址开始录制")
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                Spacer()
            }
        }
        .padding()
    }
    
    private func startRecord() {
        guard !streamUrl.isEmpty else { return }
        backend.startRecord(url: streamUrl, title: title, maxDuration: maxDuration)
        streamUrl = ""
    }
}

struct RecordTaskRow: View {
    let task: RecordTask
    
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(task.title)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                StatusBadge(status: task.status)
            }
            
            Text(task.progress)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}
