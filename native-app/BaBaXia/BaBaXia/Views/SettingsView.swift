import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var backend: BackendService
    @AppStorage("llmUrl") private var llmUrl = "http://127.0.0.1:8080"
    @AppStorage("llmModel") private var llmModel = "gemma-4"
    @AppStorage("apiKey") private var apiKey = ""
    @AppStorage("frameInterval") private var frameInterval = "30"
    @AppStorage("maxTokens") private var maxTokens = "4096"
    @AppStorage("temperature") private var temperature = "0.3"
    @AppStorage("proxy") private var proxy = ""
    @AppStorage("outputDir") private var outputDir = ""
    
    var body: some View {
        Form {
            Section("LLM 设置") {
                TextField("API 地址", text: $llmUrl)
                    .textFieldStyle(.roundedBorder)
                TextField("模型名称", text: $llmModel)
                    .textFieldStyle(.roundedBorder)
                SecureField("API Key（可选）", text: $apiKey)
                    .textFieldStyle(.roundedBorder)
            }
            
            Section("分析参数") {
                HStack(spacing: 16) {
                    VStack(alignment: .leading) {
                        Text("抽帧间隔（秒）").font(.caption).foregroundStyle(.secondary)
                        TextField("30", text: $frameInterval)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 80)
                    }
                    VStack(alignment: .leading) {
                        Text("Max Tokens").font(.caption).foregroundStyle(.secondary)
                        TextField("4096", text: $maxTokens)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 80)
                    }
                    VStack(alignment: .leading) {
                        Text("Temperature").font(.caption).foregroundStyle(.secondary)
                        TextField("0.3", text: $temperature)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 80)
                    }
                }
            }
            
            Section("网络") {
                TextField("代理（如 socks5://127.0.0.1:7890）", text: $proxy)
                    .textFieldStyle(.roundedBorder)
            }
            
            Section("存储") {
                HStack {
                    TextField("下载/输出目录", text: $outputDir)
                        .textFieldStyle(.roundedBorder)
                    Button("选择") { browseOutputDir() }
                }
                Text("留空使用默认（~/Downloads/vgrab-web）")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            
            Section {
                HStack {
                    Circle()
                        .fill(backend.isBackendRunning ? .green : .red)
                        .frame(width: 8, height: 8)
                    Text(backend.isBackendRunning ? "后端服务运行中" : "后端服务未启动")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 480, height: 500)
    }
    
    private func browseOutputDir() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            outputDir = url.path
        }
    }
}
