import SwiftUI

struct ContentView: View {
    @State private var selectedTab = 0
    
    var body: some View {
        TabView(selection: $selectedTab) {
            DownloadView()
                .tabItem {
                    Label("下载", systemImage: "arrow.down.circle.fill")
                }
                .tag(0)
            
            TranscribeView()
                .tabItem {
                    Label("转录", systemImage: "waveform")
                }
                .tag(1)
            
            AnalyzeView()
                .tabItem {
                    Label("分析", systemImage: "eye.fill")
                }
                .tag(2)
            
            RecordView()
                .tabItem {
                    Label("录制", systemImage: "record.circle")
                }
                .tag(3)
        }
        .padding()
    }
}
