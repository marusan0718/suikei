import SwiftUI

@main
struct SuikeiNativeApp: App {
    @StateObject private var audioEngine = SuikeiAudioEngine()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(audioEngine)
        }
    }
}
