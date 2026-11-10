<script setup lang="ts">
import { computed,nextTick,onBeforeUnmount,onMounted,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { showFailToast } from 'vant'
import { sessionApi } from '@/api'
import type { ChatMessage } from '@/types'
import { streamChat } from '@/utils/sse'
const route=useRoute();const router=useRouter()
const messages=ref<ChatMessage[]>([])
const input=ref('')
const loading=ref(false)
const streaming=ref(false)
const scroller=ref<HTMLDivElement>()
const controller=ref<AbortController|null>(null)
const sessionId=ref<number|undefined>(route.params.sessionId?Number(route.params.sessionId):undefined)
const documentId=ref<number|undefined>(route.query.document_id?Number(route.query.document_id):undefined)
const welcome=computed(()=>messages.value.length===0)
function render(text:string){return DOMPurify.sanitize(marked.parse(text||'') as string)}
async function scrollBottom(){await nextTick();if(scroller.value)scroller.value.scrollTop=scroller.value.scrollHeight}
async function load(){
  if(!sessionId.value)return
  loading.value=true
  try{const r=await sessionApi.messages(sessionId.value);messages.value=r.data.data.messages}
  catch(e){showFailToast((e as Error).message)}
  finally{loading.value=false;scrollBottom()}
}
async function send(text?:string){
  const question=(text??input.value).trim()
  if(!question||streaming.value)return
  input.value='';streaming.value=true;controller.value=new AbortController()
  const assistant:ChatMessage={role:'ASSISTANT',content:'',status:'SUCCESS',suggestions:[]}
  messages.value.push({role:'USER',content:question},assistant)
  scrollBottom()
  try{
    await streamChat({question,session_id:sessionId.value,document_id:documentId.value,enable_web:true,enable_db_tool:true,stream:true},event=>{
      if(event.event==='delta')assistant.content+=event.data.content||''
      else if(event.event==='suggestion')assistant.suggestions=event.data.suggestions||[]
      else if(event.event==='done'){
        assistant.message_id=event.data.message_id
        assistant.status='SUCCESS'
        assistant.suggestions=event.data.suggestions||assistant.suggestions
        if(!sessionId.value){sessionId.value=event.data.session_id;router.replace(`/app/chat/${event.data.session_id}`)}
      }
      else if(event.event==='error'){
        assistant.status='FAILED'
        const text='回答暂时没能生成，请稍后再试，或换个说法提问。'
        assistant.content+=`\n\n${text}`
        showFailToast(text)
      }
      scrollBottom()
    },controller.value.signal)
  }catch(e:any){
    if(e.name==='AbortError'){assistant.status='FAILED';assistant.content+=assistant.content?'\n\n（已停止生成）':'（已停止生成）'}
    else{assistant.status='FAILED';assistant.content+='\n\n网络连接失败，请检查网络后重试。';showFailToast('网络连接失败，请稍后重试')}
  }finally{streaming.value=false;controller.value=null;scrollBottom()}
}
function stop(){controller.value?.abort()}
function onAction(){if(streaming.value)stop();else send()}
onMounted(load)
onBeforeUnmount(()=>controller.value?.abort())
</script>
<template>
  <div class="cc-chat">
    <header class="cc-chat-head"><button class="cc-back" @click="router.push('/app/home')">‹</button><div><span class="cc-eyebrow">校园卡助手</span><h2>{{sessionId?'继续咨询':'智能问答'}}</h2></div><span class="cc-online">在线</span></header>
    <div ref="scroller" class="cc-scroll">
      <van-loading v-if="loading" class="cc-loading" />
      <section v-if="welcome" class="cc-welcome">
        <div class="cc-orb">AI</div>
        <h2>有什么校园卡问题？</h2>
        <p>直接描述你的情况即可，我会给出简洁的办理建议；涉及账户操作时只提供指引，不会替你操作。</p>
        <div class="cc-prompts">
          <button @click="send('校园卡丢失后应该怎么补办？')">校园卡丢失后应该怎么补办？</button>
          <button @click="send('校园卡有哪些充值方式？')">校园卡有哪些充值方式？</button>
          <button @click="send('校园卡消费范围包括哪些？')">校园卡消费范围包括哪些？</button>
        </div>
      </section>
      <template v-for="(message,index) in messages" :key="message.message_id||index">
        <div :class="['cc-row',message.role==='USER'?'is-user':'is-ai']">
          <div v-if="message.role==='ASSISTANT'" class="cc-avatar">AI</div>
          <div class="cc-bubble">
            <div v-if="message.content" class="cc-markdown" v-html="render(message.content)"></div>
            <div v-else class="cc-typing"><i></i><i></i><i></i></div>
            <div v-if="message.role==='ASSISTANT'&&message.suggestions?.length&&!streaming" class="cc-suggestions">
              <p>你还可以问</p>
              <button v-for="item in message.suggestions" :key="item" @click="send(item)">{{item}}</button>
            </div>
          </div>
        </div>
      </template>
    </div>
    <footer class="cc-input-bar">
      <van-field v-model="input" class="cc-input" type="textarea" rows="1" autosize :disabled="streaming" maxlength="1000" placeholder="输入你的问题，最多1000字" />
      <button class="cc-send" :class="{stop:streaming}" :disabled="!streaming&&!input.trim()" @click="onAction">{{streaming?'停止':'发送'}}</button>
    </footer>
  </div>
</template>
<style scoped>
.cc-chat{height:calc(100vh - 60px);display:flex;flex-direction:column;background:linear-gradient(180deg,#eef7f6,#f7fafb 32%)}
.cc-chat-head{height:70px;display:flex;align-items:center;gap:11px;padding:12px 16px;background:rgba(255,255,255,.94);backdrop-filter:blur(14px);border-bottom:1px solid #e1ebee;flex:0 0 auto}
.cc-chat-head>div{flex:1}.cc-chat-head h2{margin:2px 0 0;font-size:17px}
.cc-eyebrow{font-size:9px;letter-spacing:.12em;color:#70899a;font-weight:800}
.cc-back{width:35px;height:35px;border:0;border-radius:12px;background:#e9f3f3;color:#0f6e69;font-size:25px}
.cc-online{font-size:10px;color:#0f756f;background:#e8f6f1;border-radius:999px;padding:4px 9px}
.cc-scroll{flex:1;overflow-y:auto;padding:18px 14px 24px}
.cc-loading{display:flex;justify-content:center;padding:30px 0}
.cc-welcome{text-align:center;padding:40px 8px}
.cc-orb{width:70px;height:70px;border-radius:25px;background:linear-gradient(135deg,#0f756f,#60bab1);box-shadow:0 15px 35px rgba(15,124,115,.25);display:grid;place-items:center;margin:0 auto 18px;color:white;font-size:20px;font-weight:800}
.cc-welcome h2{font-size:24px;margin:0 0 8px}.cc-welcome>p{font-size:13px;color:#728995;line-height:1.7;margin:0 auto;max-width:330px}
.cc-prompts{display:grid;gap:9px;margin:24px auto 0;max-width:360px}.cc-prompts button{border:1px solid #dce9eb;background:white;border-radius:14px;padding:12px 14px;text-align:left;color:#284b5a;font-size:13px}
.cc-row{display:flex;gap:9px;margin-bottom:16px;align-items:flex-start}.cc-row.is-user{justify-content:flex-end}
.cc-avatar{width:34px;height:34px;border-radius:12px;background:linear-gradient(135deg,#0f756f,#4aa79f);color:white;display:grid;place-items:center;font-size:11px;font-weight:800;flex:0 0 auto}
.cc-bubble{max-width:82%;border-radius:18px;padding:12px 14px;font-size:14px;line-height:1.7;word-break:break-word}
.is-ai .cc-bubble{background:white;color:#1e4052;box-shadow:0 7px 20px rgba(25,68,88,.06);border-top-left-radius:6px}
.is-user .cc-bubble{background:#0f7c73;color:white;border-top-right-radius:6px}
.cc-markdown :deep(p){margin:0 0 8px}.cc-markdown :deep(p:last-child){margin-bottom:0}.cc-markdown :deep(ul),.cc-markdown :deep(ol){padding-left:20px;margin:6px 0}
.cc-markdown :deep(h1),.cc-markdown :deep(h2),.cc-markdown :deep(h3),.cc-markdown :deep(h4){font-size:14px;margin:10px 0 6px;font-weight:700}
.cc-markdown :deep(code){background:#eef4f6;border-radius:4px;padding:1px 4px;font-size:12px}
.cc-markdown :deep(a){color:#0f7c73;text-decoration:none}
.cc-typing{display:flex;gap:4px;padding:3px 0}.cc-typing i{width:6px;height:6px;border-radius:50%;background:#9ab8b8;animation:cc-blink 1s infinite}.cc-typing i:nth-child(2){animation-delay:.15s}.cc-typing i:nth-child(3){animation-delay:.3s}
@keyframes cc-blink{0%,80%,100%{opacity:.25}40%{opacity:1}}
.cc-suggestions{margin-top:12px;padding-top:10px;border-top:1px dashed #e4eef0}.cc-suggestions p{margin:0 0 7px;font-size:10px;color:#93a4ad}
.cc-suggestions button{display:block;width:100%;text-align:left;border:1px solid #dcebe8;background:#f7fcfb;border-radius:11px;padding:9px 11px;margin-bottom:6px;color:#2b5a60;font-size:12px}
.cc-input-bar{flex:0 0 auto;display:flex;gap:9px;align-items:flex-end;padding:10px 14px calc(12px + env(safe-area-inset-bottom));background:white;border-top:1px solid #e1ebee}
.cc-input{flex:1;background:#f4f8fa;border-radius:15px;padding:4px 10px;max-height:110px;overflow-y:auto}
.cc-send{border:0;border-radius:14px;background:#0f7c73;color:white;font-size:14px;padding:11px 16px;flex:0 0 auto}
.cc-send:disabled{opacity:.45}.cc-send.stop{background:#c0392b}
</style>
