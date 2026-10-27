# 本地 RVC 声线

网页的“回复语音”选择器提供 Edge TTS 普通声线、`我的合成声线（MiMo）` 和 `Ayaka_RVC（本地模型）`；点击旁边的“试听”可播放当前选中的声线，试听 Ayaka 需要本地 RVC 服务已启动。MiMo 选项使用 `extract_radio/` 中的个人参考音频与 `mimo-v2.5-tts-voiceclone` 模型；克隆模式使用 WAV 输出格式并将本地参考音频作为 data URI 传入。若 `MIMO_TTS_MODEL` 指向 voiceclone 模型且未显式设置 `MIMO_TTS_PROFILE`，后端自动使用 clone 模式。“服务器默认”仍使用 Edge TTS 的晓晓声线（`zh-CN-XiaoxiaoNeural`）。

## 模型与授权

可推理模型来自 [Hanazar-Games/RVC-voice-models 的 4Ayaka Release](https://github.com/Hanazar-Games/RVC-voice-models/releases/tag/4Ayaka)，Release 资产 `Ayaka_RVC.pth`。此项目 README 声明模型仓库采用 CC BY-NC 4.0，并注明角色及原始语音版权归 HoYoverse。模型仅限遵守其许可的个人、学习和非商业用途；使用或再分发时请注明模型作者/来源，并自行确认相关权利要求。

`Ayaka_RVC/` 中训练得到的 `G_*.pth`、`D_*.pth` 是训练检查点，不是可直接加载的推理模型。推理需使用 `Ayaka_RVC.pth` 和目录里的 `added_IVF*_index` 索引文件。推理权重不会提交到 Git。

如果在其他副本/服务器部署，需先准备模型资产：从上述 Release 下载 `Ayaka_RVC.pth` 到 `Ayaka_RVC/`，并将原模型目录中的 `added_IVF804_Flat_nprobe_1_Ayaka_RVC_v2.index` 一并复制过去。整个 `Ayaka_RVC/` 目录因包含大型训练数据而被 Git 忽略。

## 安装并启动本地转换服务（Windows）

RVC 推理依赖需要独立环境，不要安装到项目虚拟环境。当前工作区使用 Python 3.11；sidecar 会在进程内为旧版 fairseq/Hydra 启用 dataclass 兼容处理，不会修改安装的第三方包。主项目环境还需要安装 `requirements.txt` 中的 `edge-tts`，否则普通声线和 Ayaka 的基础语音都无法合成：

```powershell
py -3.11 -m venv "$env:LOCALAPPDATA\agent-competition-rvc-py311"
$rvcPython = "$env:LOCALAPPDATA\agent-competition-rvc-py311\Scripts\python.exe"
& $rvcPython -m pip install -r requirements-rvc.txt
```

首次启动 sidecar 时，项目会从 Hugging Face 下载必需的 HuBERT 推理文件（约 181 MiB）到独立环境的 `Lib\site-packages\rvc_python\base_model\hubert_base.pt`；请确保该地址可访问。当前固定使用 Harvest 提取音高，不需要额外下载 RMVPE 文件。下载完成后该文件会保留在本机供后续启动使用。

在项目根目录另开一个终端启动服务。默认使用 CPU；如有正确配置的 CUDA/PyTorch，可将 `--device cpu` 改为 `--device cuda:0`。

```powershell
$rvcPython = "$env:LOCALAPPDATA\agent-competition-rvc-py311\Scripts\python.exe"
& $rvcPython -m backend.voice.rvc_sidecar `
  --model "$PWD\Ayaka_RVC\Ayaka_RVC.pth" `
  --index "$PWD\Ayaka_RVC\added_IVF804_Flat_nprobe_1_Ayaka_RVC_v2.index" `
  --device cpu --port 5050
```

项目自带的 sidecar 明确绑定 `127.0.0.1`，并将转换请求限制为 20 MB。项目后端默认连接 `http://127.0.0.1:5050/convert`；如修改端口，可设置环境变量 `RVC_API_URL`，但只允许本机回环地址。启动 Flask 后端后，在网页选择 **Ayaka_RVC（本地模型）** 即可。RVC 推理在 CPU 上可能明显慢于标准语音；模型服务未启动或转换失败时，接口会返回明确错误，不会静默回退到其他声线。

## 来源

- 模型 Release: <https://github.com/Hanazar-Games/RVC-voice-models/releases/tag/4Ayaka>
- RVC Python: <https://pypi.org/project/rvc-python/>
