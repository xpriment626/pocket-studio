// Test host only: the app itself always uses the official bridge.
import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge';
window.startReview = async (html, result) => {
  const frame = document.createElement('iframe');
  frame.setAttribute('sandbox','allow-scripts allow-same-origin');
  frame.style.cssText='width:950px;height:1000px';
  document.body.append(frame);
  const bridge = new AppBridge(null,{name:'Browser test host',version:'1'},{serverTools:{}});
  bridge.oncalltool = params => window.callTool(params);
  bridge.oninitialized = async () => {
    await bridge.sendToolInput({arguments:{ids:result.structuredContent.versions.map(x=>x.id)}});
    await bridge.sendToolResult(result);
  };
  await bridge.connect(new PostMessageTransport(frame.contentWindow,frame.contentWindow));
  frame.srcdoc = html;
};
