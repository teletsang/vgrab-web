import SwiftUI

@main
struct BaBaXiaApp: App {
    @StateObject private var backendService = BackendService()
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(backendService)
                .frame(minWidth: 700, minHeight: 520)
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 800, height: 600)
        
        Settings {
            SettingsView()
                .environmentObject(backendService)
        }
    }
}
