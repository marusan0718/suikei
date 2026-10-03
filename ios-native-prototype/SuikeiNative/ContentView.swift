import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var audio: SuikeiAudioEngine

    @State private var speedNorm = 0.5
    @State private var levelCm = 120.0
    @State private var slack = false

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 28) {
                Spacer()

                VStack(spacing: 8) {
                    Text("水景")
                        .font(.system(size: 34, weight: .medium, design: .rounded))

                    Text("Native Route Test")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                VStack(spacing: 14) {
                    HStack(spacing: 14) {
                        AirPlayRoutePicker()
                            .frame(width: 46, height: 46)

                        VStack(alignment: .leading, spacing: 3) {
                            Text("再生出力先")
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Text(audio.routeName)
                                .font(.callout.weight(.medium))
                        }

                        Spacer()
                    }

                    Button {
                        if audio.isRunning {
                            audio.stop()
                        } else {
                            audio.start()
                            applyTide()
                        }
                    } label: {
                        Text(audio.isRunning ? "停止" : "再生")
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                    }
                    .buttonStyle(.borderedProminent)
                }
                .padding(18)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 22))

                VStack(spacing: 20) {
                    controlRow(
                        title: "潮流速度",
                        valueText: "\(Int(speedNorm * 100))%"
                    ) {
                        Slider(value: $speedNorm, in: 0...1)
                    }

                    controlRow(
                        title: "潮位",
                        valueText: "\(Int(levelCm)) cm"
                    ) {
                        Slider(value: $levelCm, in: 20...230)
                    }

                    Toggle("潮止まり", isOn: $slack)
                }
                .padding(18)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 22))

                if let error = audio.errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                }

                Text("第1層をリアルタイム合成中。HomePodを選んだまま潮流速度を動かして、音が途切れず変化するか確認します。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)

                Spacer()
            }
            .padding(24)
            .frame(maxWidth: 620)
        }
        .preferredColorScheme(.dark)
        .onChange(of: speedNorm) { _, _ in applyTide() }
        .onChange(of: levelCm) { _, _ in applyTide() }
        .onChange(of: slack) { _, _ in applyTide() }
    }

    @ViewBuilder
    private func controlRow<Content: View>(
        title: String,
        valueText: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(spacing: 8) {
            HStack {
                Text(title)
                Spacer()
                Text(valueText)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }

            content()
        }
    }

    private func applyTide() {
        audio.setTide(
            speedNorm: speedNorm,
            levelCm: levelCm,
            slack: slack
        )
    }
}
