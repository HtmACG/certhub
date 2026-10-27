<!--
  流水线画布（Vue Flow）
  =========================================================
  为什么用 Vue Flow（@vue-flow/core，MIT，GitHub: bcakmakoglu/vue-flow）：
  1. 它是 React Flow 的 Vue3 移植，节点 / 连线 / 缩放 / 小地图都是现成的，
     不用自己算贝塞尔曲线和拖拽矩阵；
  2. 支持自定义节点（#node-xxx 插槽）与 parentNode 分组，正好对上
     「阶段包住任务」的数据结构；
  3. 纯 SVG + CSS 变量，暗色模式直接吃 --g-* 令牌。

  映射规则：
    stage（阶段）  → group 节点（浅色虚线容器 + 顶部标题条）
    task（任务）   → 任务卡片节点（挂在 stage 下，parentNode）
    stage 内顺序   → 相邻任务之间的连线
    stage 之间     → 上一阶段最后一个任务 → 下一阶段第一个任务

  「连线拼接」：从任务右侧圆点拖到另一个任务，等于把后者排到前者后面
  （同阶段内重排 / 跨阶段搬运）。执行顺序由数组顺序决定，连线只是它的可视化，
  所以不会出现环。
-->
<template>
  <div
    ref="canvasRef"
    class="pipeline-canvas"
    :class="{ 'is-running': running }"
    :style="{ height: canvasHeight }"
  >
    <VueFlow
      id="certd-pipeline-flow"
      class="flow"
      :nodes="flowNodes"
      :edges="flowEdges"
      :default-edge-options="defaultEdgeOptions"
      :min-zoom="0.3"
      :max-zoom="1.8"
      :nodes-draggable="nodesDraggable && !readonly"
      :nodes-connectable="!readonly"
      :edges-updatable="false"
      :delete-key-code="null"
      :zoom-on-double-click="false"
      :connection-radius="28"
      :connection-line-options="connectionLineOptions"
      :progression-line-options="connectionLineOptions"
      @connect="onConnect"
      @connect-start="onConnectStart"
      @connect-end="onConnectEnd"
      @edge-click="onEdgeClick"
      @node-drag-stop="onDragStop"
      @nodes-initialized="onNodesInitialized"
      @node-dblclick="onNodeDblClick"
    >
      <Background :gap="16" :size="1.5" pattern-color="#cfd4dc" variant="dots" />
      <Controls :show-interactive="false" position="bottom-left" />
      <MiniMap
        position="bottom-right"
        :node-color="miniMapColor"
        :node-stroke-width="1"
        pannable
        zoomable
      />

      <!-- 连线：贝塞尔 + 中点圆点 -->
      <template #edge-pipeline="edgeProps">
        <PipelineEdge v-bind="edgeProps" />
      </template>

      <!-- 阶段容器 -->
      <template #node-stage="nodeProps">
        <div
          class="flow-node stage-node"
          :class="[
            'kind-' + nodeProps.data.kindKey,
            nodeProps.data.stateClass,
            { 'is-off': nodeProps.data.disabled }
          ]"
          :style="{
            width: nodeProps.data.width + 'px',
            height: nodeProps.data.height + 'px',
            '--stage-color': nodeProps.data.color
          }"
        >
          <!-- 头部：阶段序号 / 名称 / 环节；操作按钮是 hover 浮层，不占布局 -->
          <div class="stage-node-head">
            <span class="stage-node-index">{{ nodeProps.data.index }}</span>
            <span class="stage-node-title" :title="nodeProps.data.title">
              {{ nodeProps.data.title }}
            </span>
            <span class="stage-node-kind">{{ nodeProps.data.kindText }}</span>
            <span class="stage-node-spacer"></span>
            <!--
              阶段启停：常驻显示（它本身是状态指示，藏进 hover 浮层就看不出来了）。
              关掉后整段跳过 —— 引擎按 stage.enabled === false 直接 continue，
              不用逐个关阶段里的任务。nodrag 必须有，否则按住开关会拖动整个阶段框。
            -->
            <button
              type="button"
              class="stage-node-switch nodrag"
              :class="{ 'is-on': !nodeProps.data.disabled }"
              role="switch"
              :aria-checked="!nodeProps.data.disabled"
              :aria-label="nodeProps.data.disabled ? '启用该阶段' : '停用该阶段'"
              :title="
                nodeProps.data.disabled
                  ? '该阶段已停用：运行时会整段跳过，点击启用'
                  : '启停该阶段：关闭后运行时会整段跳过'
              "
              @click.stop="nodeProps.data.cb.toggle()"
            >
              <i class="knob"></i>
            </button>
            <div class="stage-node-actions nodrag">
              <button
                type="button"
                title="单独运行本阶段"
                :disabled="
                  !nodeProps.data.count || nodeProps.data.anyRunActive || nodeProps.data.disabled
                "
                @click.stop="nodeProps.data.cb.run()"
              >
                <ArtSvgIcon icon="ri:play-line" />
              </button>
              <button type="button" title="重命名阶段" @click.stop="nodeProps.data.cb.rename()">
                <ArtSvgIcon icon="ri:pencil-line" />
              </button>
              <button type="button" title="查看本阶段日志" @click.stop="nodeProps.data.cb.log()">
                <ArtSvgIcon icon="ri:terminal-box-line" />
              </button>
              <button
                type="button"
                class="is-danger"
                title="删除阶段"
                @click.stop="nodeProps.data.cb.remove()"
              >
                <ArtSvgIcon icon="ri:delete-bin-5-line" />
              </button>
            </div>
          </div>

          <!--
            「添加任务」做成阶段底部常驻按钮。
            之前只放在头部 hover 浮层里（opacity: 0），24px 的图标藏在右上角，
            实际根本点不到 —— 用户反馈的「画布模式加不了任务」就是这个。
          -->
          <button
            v-if="nodeProps.data.canAdd"
            type="button"
            class="stage-node-add nodrag"
            @click.stop="nodeProps.data.cb.add()"
          >
            <ArtSvgIcon icon="ri:add-line" />
            <span>{{ nodeProps.data.addText }}</span>
            <em>{{ nodeProps.data.taskCount }}/{{ nodeProps.data.maxTasks }}</em>
          </button>
          <div v-else class="stage-node-limit nodrag">
            <ArtSvgIcon icon="ri:checkbox-circle-line" />
            <span>本阶段已满 {{ nodeProps.data.maxTasks }} 个任务</span>
          </div>
        </div>
      </template>

      <!-- 任务卡片 -->
      <template #node-task="nodeProps">
        <div
          class="flow-node task-node"
          :class="[
            'kind-' + nodeProps.data.kindKey,
            nodeProps.data.stateClass,
            {
              'is-disabled': nodeProps.data.disabled,
              'is-stage-off': nodeProps.data.stageOff,
              'is-selected': nodeProps.selected
            }
          ]"
          :style="{
            '--node-color': nodeProps.data.color,
            width: nodeProps.data.width + 'px',
            height: nodeProps.data.height + 'px'
          }"
          @dblclick.stop="nodeProps.data.cb.open()"
        >
          <!-- 入口只有一个：顺序连线和「失败后」连线都从左侧这个 in 进来 -->
          <Handle type="target" :position="Position.Left" id="in" class="flow-handle is-in" />
          <!--
            出口两个，上下分开：
            · 上（out）「成功后」：顺着执行链继续往下走；
            · 下（err）「失败后」：这一步挂了直接跳到后面指定的任务。
            两条线用同一套线型（蓝色实线 + 中点圆点），靠端口位置和标签区分语义。
          -->
          <Handle type="source" :position="Position.Right" id="out" class="flow-handle is-out" />
          <span class="flow-port-label is-out">成功后</span>
          <Handle
            type="source"
            :position="Position.Right"
            id="err"
            class="flow-handle is-err"
            :class="{ 'is-on': nodeProps.data.hasErrorLink }"
          />
          <span class="flow-port-label is-err" :class="{ 'is-on': nodeProps.data.hasErrorLink }">
            失败后
          </span>
          <!--
            同阶段内是上下排列，连线走「底部 → 顶部」才自然；
            这两个锚点只给程序连线用，不参与用户拖拽（is-ghost 透明且不接收指针）。
          -->
          <Handle type="target" :position="Position.Top" id="in-top" class="flow-handle is-ghost" />
          <Handle
            type="source"
            :position="Position.Bottom"
            id="out-bottom"
            class="flow-handle is-ghost"
          />

          <div class="task-node-head">
            <span class="task-node-icon">
              <BrandAvatar
                :logo-file="nodeProps.data.logoFile"
                :logo="nodeProps.data.logo"
                :short="nodeProps.data.short"
                :color="nodeProps.data.color"
                :name="nodeProps.data.pluginName"
                :size="26"
              />
            </span>
            <div class="task-node-title-wrap">
              <span class="task-node-title" :title="nodeProps.data.title">
                {{ nodeProps.data.title }}
              </span>
              <span class="task-node-sub">{{ nodeProps.data.subtitle }}</span>
            </div>
            <span
              v-if="nodeProps.data.statusText"
              class="task-node-state"
              :class="'is-' + nodeProps.data.statusKey"
            >
              <i class="dot"></i>{{ nodeProps.data.statusText }}
            </span>
            <span v-else-if="nodeProps.data.disabled" class="task-node-state is-off">
              <i class="dot"></i>已停用
            </span>
            <!-- 没连线的步骤不会被执行，必须在卡片上直接说出来，不然用户以为它在跑 -->
            <span v-else-if="nodeProps.data.unlinked" class="task-node-state is-unlinked">
              <i class="dot"></i>未连线
            </span>
          </div>

          <p class="task-node-desc" :title="nodeProps.data.desc">{{ nodeProps.data.desc }}</p>

          <dl class="task-node-meta">
            <div v-for="row in nodeProps.data.meta" :key="row.label" class="task-node-meta-row">
              <dt>{{ row.label }}</dt>
              <dd :title="row.value">{{ row.value }}</dd>
            </div>
          </dl>

          <div class="task-node-foot">
            <span class="task-node-seq">{{ nodeProps.data.seq }}</span>
            <span class="task-node-foot-text" :title="nodeProps.data.footText">
              {{ nodeProps.data.footText }}
            </span>
            <div class="task-node-actions nodrag" @dblclick.stop>
              <button type="button" title="查看该任务日志" @click.stop="nodeProps.data.cb.log()">
                <ArtSvgIcon icon="ri:terminal-box-line" />
              </button>
              <button type="button" title="配置参数" @click.stop="nodeProps.data.cb.open()">
                <ArtSvgIcon icon="ri:settings-3-line" />
              </button>
              <button
                type="button"
                class="is-danger"
                title="删除任务"
                @click.stop="nodeProps.data.cb.remove()"
              >
                <ArtSvgIcon icon="ri:delete-bin-5-line" />
              </button>
            </div>
          </div>
        </div>
      </template>
    </VueFlow>

    <!-- 空画布提示：新建流水线时别只留一片点阵 -->
    <div v-if="!stages.length" class="canvas-empty">
      <ArtSvgIcon icon="ri:flow-chart" class="canvas-empty-icon" />
      <p class="canvas-empty-title">还没有阶段</p>
      <p class="canvas-empty-desc"
        >先添加一个阶段（比如「申请证书」），再往里放任务；任务之间可以连线拼接顺序。</p
      >
    </div>

    <!-- 画布左上角：操作提示 + 视图动作 -->
    <div class="canvas-toolbar">
      <div class="canvas-toolbar-hint">
        <ArtSvgIcon icon="ri:information-line" />
        右上开关 = 启停阶段 · 右侧上点 = 成功后 · 右侧下点 = 失败后 · 点连线 = 删除 · 双击卡片 =
        配置 · 拖标题条 = 移动阶段
      </div>
      <div class="canvas-toolbar-actions">
        <ElTooltip content="缩放到适合窗口" placement="bottom">
          <button type="button" @click="fitAll">
            <ArtSvgIcon icon="ri:fullscreen-line" />
            <span>适应窗口</span>
          </button>
        </ElTooltip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { Handle, Position, VueFlow, useVueFlow } from '@vue-flow/core'
  import type { Connection, Edge, Node } from '@vue-flow/core'
  import { Background } from '@vue-flow/background'
  import { Controls } from '@vue-flow/controls'
  import { MiniMap } from '@vue-flow/minimap'
  import '@vue-flow/core/dist/style.css'
  import '@vue-flow/core/dist/theme-default.css'
  import '@vue-flow/controls/dist/style.css'
  import '@vue-flow/minimap/dist/style.css'
  import BrandAvatar from '../../components/brand-avatar.vue'
  import PipelineEdge from './pipeline-edge.vue'
  import {
    CANVAS_METRICS,
    MAX_TASKS_PER_STAGE,
    emptyLayout,
    type CanvasLayout
  } from './canvas-types'
  import type { PipelineStage, PipelineTask, TaskPlugin } from '@/api/certd'

  defineOptions({ name: 'PipelineCanvas' })

  const props = withDefaults(
    defineProps<{
      stages: PipelineStage[]
      pluginOf: (type: string) => TaskPlugin | undefined
      /** 上次执行状态：{ key: 'success' | 'failed' | 'running' | 'skipped', text } */
      statusOf: (taskId: string) => { key: string; text: string } | null
      /** 阶段整体状态 class：is-success / is-failed / is-running */
      stageStateOf: (stage: PipelineStage) => string
      /** 任务摘要（最多两行）：[{ label, value }] */
      metaOf: (task: PipelineTask) => { label: string; value: string }[]
      layout?: CanvasLayout
      running?: boolean
      readonly?: boolean
      anyRunActive?: boolean
      /**
       * 节点能否拖动。
       * 现在**只放开阶段外框**：外框可以拖到任意位置（位置落进 content.layout），
       * 里面的任务卡片永远 draggable: false —— 卡片位置由「阶段内顺序」决定，
       * 拖动外框时卡片跟着整体走（parentNode 自带）。
       */
      nodesDraggable?: boolean
      /** 底部日志终端展开时占掉的高度：画布要让位，否则卡片被终端压住 */
      bottomOffset?: number
    }>(),
    {
      layout: () => emptyLayout(),
      running: false,
      readonly: false,
      anyRunActive: false,
      nodesDraggable: true,
      bottomOffset: 0
    }
  )

  const emit = defineEmits<{
    (e: 'open-task', stageIndex: number, taskIndex: number): void
    (e: 'task-log', stageIndex: number, taskIndex: number): void
    (e: 'task-delete', stageIndex: number, taskIndex: number): void
    (e: 'task-add', stageIndex: number): void
    (e: 'stage-run', stageIndex: number): void
    (e: 'stage-log', stageIndex: number): void
    (e: 'stage-rename', stageIndex: number): void
    (e: 'stage-delete', stageIndex: number): void
    /** 阶段启停：true = 启用，false = 停用（运行时整段跳过） */
    (e: 'stage-toggle', stageIndex: number, enabled: boolean): void
    (
      e: 'connect-task',
      payload: { sourceTaskId: string; targetTaskId: string; kind?: 'reorder' | 'error' }
    ): void
    (
      e: 'edge-delete',
      payload: { sourceTaskId: string; targetTaskId: string; kind: 'next' | 'error' }
    ): void
    (e: 'layout-change', layout: CanvasLayout): void
  }>()

  /* ---------------- 布局常量（唯一来源：canvas-types.ts） ---------------- */
  const {
    nodeWidth: NODE_W,
    nodeHeight: NODE_H,
    stageHead: STAGE_HEAD,
    stagePadX: STAGE_PAD_X,
    stagePadRight: STAGE_PAD_RIGHT,
    stagePadBottom: STAGE_PAD_B,
    gapY: GAP_Y,
    gapX: GAP_X,
    addButtonHeight: ADD_BTN_H,
    addButtonGap: ADD_BTN_GAP
  } = CANVAS_METRICS
  /** 右侧多留 stagePadRight：两个出口的「成功后 / 失败后」标签写在卡片外的这段留白里 */
  const STAGE_W = NODE_W + STAGE_PAD_X + STAGE_PAD_RIGHT

  const KIND_TEXT: Record<string, string> = {
    cert: '证书申请',
    deploy: '证书部署',
    notify: '发送通知'
  }

  const flowNodes = ref<Node[]>([])
  const flowEdges = ref<Edge[]>([])

  /** 画布内部的坐标表：初始来自 props.layout，拖动后就地更新（避免每次拖动都整图重建） */
  const positions = reactive<CanvasLayout>({
    stages: { ...(props.layout?.stages || {}) },
    tasks: { ...(props.layout?.tasks || {}) }
  })
  /** 用户是否已经动过坐标：动过之后就不再吃外部 layout，防止异步加载把位置冲掉 */
  let layoutTouched = false

  const { setViewport, getViewport } = useVueFlow('certd-pipeline-flow')

  /**
   * 画布高度：铺满「视口 - 顶部操作条 - 底部日志终端」剩下的空间，跟着浏览器窗口缩放。
   * 上下限只兜极端情况（窗口特别矮 / 特别高），中间完全自适应。
   */
  const canvasHeight = computed(() => {
    const offset = Math.max(0, Number(props.bottomOffset) || 0)
    return `clamp(440px, calc(100vh - 286px - ${offset}px), 1200px)`
  })

  /** 拖连线时的临时曲线（Vue Flow 的类型要求枚举，这里直接放开） */
  const connectionLineOptions: any = {
    type: 'bezier',
    style: { stroke: 'var(--g-blue)', strokeWidth: 2, strokeDasharray: '5 4' }
  }

  const defaultEdgeOptions = {
    type: 'bezier',
    style: { stroke: 'var(--flow-edge)', strokeWidth: 2 }
  }

  const taskKindOf = (type: string): string => {
    if (type === 'Notify') return 'notify'
    if (type.indexOf('CertApply') === 0) return 'cert'
    return 'deploy'
  }

  const stageKindKey = (stage: PipelineStage): string => {
    const first = stage.tasks?.[0]
    return first ? taskKindOf(first.type) : 'deploy'
  }

  /**
   * 阶段容器高度 = 标题条 + 卡片列 + 「添加任务」按钮 + 底部留白。
   * 满 5 个任务后按钮换成「已达上限」文字条（不可点），高度少一档。
   */
  const stageHeight = (count: number): number => {
    const cards = count * NODE_H + Math.max(0, count - 1) * GAP_Y
    const addZone = count < MAX_TASKS_PER_STAGE ? ADD_BTN_GAP + ADD_BTN_H : ADD_BTN_H
    return STAGE_HEAD + cards + addZone + STAGE_PAD_B
  }

  /** 自动布局：第 i 个阶段在 i*(阶段宽+间距) 处；组内任务纵向排开 */
  const autoStagePos = (index: number) => ({ x: index * (STAGE_W + GAP_X), y: 0 })
  const autoTaskPos = (index: number) => ({
    x: STAGE_PAD_X,
    y: STAGE_HEAD + index * (NODE_H + GAP_Y)
  })

  /**
   * 重建节点与连线。
   * 触发条件只有一个「结构签名」：阶段/任务的数量、id、标题、启停、执行状态、参数。
   * 拖动位置不算结构，不会触发重建（否则一拖就回弹）。
   */
  /**
   * 每个阶段上一次的「任务 id 序列」。
   * 序列一变（增删任务、连线拼接把任务搬进搬出），该阶段内的坐标就作废、
   * 重新按顺序排 —— 否则搬进来的任务会带着原阶段的 y 坐标，和现有卡片重叠。
   */
  const lastStageKeys = new Map<string, string>()

  const rebuild = () => {
    const nodes: Node[] = []
    const edges: Edge[] = []

    props.stages.forEach((stage, stageIndex) => {
      const stageId = 'stage:' + stage.id
      const count = stage.tasks?.length || 0
      const stagePos = positions.stages[stage.id] || autoStagePos(stageIndex)
      const kindKey = stageKindKey(stage)
      const color =
        kindKey === 'cert'
          ? 'var(--g-blue)'
          : kindKey === 'deploy'
            ? 'var(--g-green)'
            : 'var(--g-amber)'

      const taskKey = (stage.tasks || []).map((task) => task.id).join(',')
      const taskChanged = lastStageKeys.has(stage.id) && lastStageKeys.get(stage.id) !== taskKey
      lastStageKeys.set(stage.id, taskKey)
      if (taskChanged) {
        for (const task of stage.tasks || []) delete positions.tasks[task.id]
      }

      /** 阶段开关：缺省 / true 都是启用，只有明确 false 才停用 */
      const stageEnabled = stage.enabled !== false

      nodes.push({
        id: stageId,
        type: 'stage',
        position: { ...stagePos },
        draggable: props.nodesDraggable && !props.readonly,
        selectable: false,
        connectable: false,
        data: {
          kindKey,
          color,
          index: String(stageIndex + 1).padStart(2, '0'),
          title: stage.title || '未命名阶段',
          kindText: KIND_TEXT[kindKey],
          count,
          width: STAGE_W,
          height: stageHeight(count),
          stateClass: props.stageStateOf(stage),
          anyRunActive: props.anyRunActive,
          /** 阶段停用：整段跳过（卡片右上角开关控制） */
          disabled: !stageEnabled,
          canAdd: count < MAX_TASKS_PER_STAGE,
          taskCount: count,
          maxTasks: MAX_TASKS_PER_STAGE,
          addText: count ? '添加任务' : '添加第一个任务',
          cb: {
            run: () => emit('stage-run', stageIndex),
            add: () => emit('task-add', stageIndex),
            rename: () => emit('stage-rename', stageIndex),
            log: () => emit('stage-log', stageIndex),
            remove: () => emit('stage-delete', stageIndex),
            /** 抛出的是「切换后的目标状态」，页面只管赋值 + 落库 */
            toggle: () => emit('stage-toggle', stageIndex, !stageEnabled)
          }
        }
      })

      stage.tasks.forEach((task, taskIndex) => {
        const plugin = props.pluginOf(task.type)
        const status = props.statusOf(task.id)
        const kind = taskKindOf(task.type)
        const taskColor =
          kind === 'cert'
            ? 'var(--g-blue)'
            : kind === 'deploy'
              ? 'var(--g-green)'
              : 'var(--g-amber)'
        const meta = props.metaOf(task).slice(0, 2)
        const relPos = positions.tasks[task.id] || autoTaskPos(taskIndex)
        nodes.push({
          id: task.id,
          type: 'task',
          parentNode: stageId,
          extent: 'parent',
          position: { ...relPos },
          // 任务卡片永远不能单独拖：位置由「阶段内顺序」决定。
          // 外框（阶段）可以拖，拖动时卡片跟着整体走 —— 这是 parentNode 自带的。
          draggable: false,
          data: {
            kindKey: kind,
            color: plugin?.color || taskColor,
            width: NODE_W,
            height: NODE_H,
            title: task.title || plugin?.name || task.type,
            // 标题默认就是插件名，副标题再写一遍没意义 —— 这里给「环节」，底部给「技术类型」
            subtitle: KIND_TEXT[kind] || '',
            desc: plugin?.desc || '还没有填写参数，双击卡片配置',
            logoFile: plugin?.logoFile,
            logo: plugin?.logo,
            short: plugin?.short,
            pluginName: plugin?.name || task.type,
            meta,
            seq: '#' + (taskIndex + 1),
            footText: [
              task.type,
              task.linked === false ? '未连线' : '',
              task.continueOnError ? '失败继续' : '',
              task.onErrorTaskId ? '失败后跳转' : ''
            ]
              .filter(Boolean)
              .join(' · '),
            hasErrorLink: !!task.onErrorTaskId,
            /** 没连线 = 不参与执行（新加的步骤默认就是这个状态） */
            unlinked: task.linked === false,
            /** 所属阶段被关掉：卡片跟着降饱和，别让人以为这一段还在跑 */
            stageOff: !stageEnabled,
            statusKey: status?.key || '',
            statusText: status?.text || '',
            disabled: task.enabled === false,
            stateClass: status?.key ? 'is-' + status.key : '',
            cb: {
              open: () => emit('open-task', stageIndex, taskIndex),
              log: () => emit('task-log', stageIndex, taskIndex),
              remove: () => emit('task-delete', stageIndex, taskIndex)
            }
          }
        })
      })
    })

    /**
     * 执行链：只有「已连线」的任务才在链上。
     * 新加的步骤 `linked === false`，画布上不给它画线、运行时也会跳过；
     * 用户从别处拖一条蓝线到它身上，它才进入执行链（见 detail.vue 的 onCanvasConnect）。
     */
    const ordered: { task: PipelineTask; stageId: string }[] = []
    for (const stage of props.stages) {
      // 阶段被关掉 = 整段不在执行链上：跳过它，前后两个「活着」的任务直接连起来。
      // 不跳的话线会从停用的阶段里穿过去，看着像它还会执行。
      if (stage.enabled === false) continue
      for (const task of stage.tasks || []) {
        if (task.linked === false) continue
        ordered.push({ task, stageId: stage.id })
      }
    }
    for (let i = 0; i < ordered.length - 1; i++) {
      const from = ordered[i]
      const to = ordered[i + 1]
      const live =
        props.statusOf(from.task.id)?.key === 'running' ||
        props.statusOf(to.task.id)?.key === 'running'
      // 同阶段：底部 → 顶部（竖排卡片之间的短线）；跨阶段：右侧 → 左侧（横向跨栏）
      const sameStage = from.stageId === to.stageId
      edges.push({
        id: 'edge:' + from.task.id + '->' + to.task.id,
        source: from.task.id,
        target: to.task.id,
        sourceHandle: sameStage ? 'out-bottom' : 'out',
        targetHandle: sameStage ? 'in-top' : 'in',
        type: 'pipeline',
        animated: live,
        class: live ? 'flow-edge is-live' : 'flow-edge',
        style: { stroke: 'var(--flow-edge)', strokeWidth: 2 }
      })
    }

    /**
     * 「失败后」跳转的连线。
     * 线型与上方的顺序连线完全一致（蓝色实线 + 中点圆点、同样的 2px 描边与贝塞尔曲线），
     * 语义只靠出口位置区分：从卡片右侧下方的「失败后」端口出发，
     * 进入目标卡片唯一的输入口。跨阶段时也是直接连过去，不再绕底部通道。
     * 它表达的不是顺序，而是「这一步挂了就去跑那一步」，所以可以跨阶段。
     */
    /** 全部任务（含未连线的）：错误连线只要求目标存在，不要求在链上 */
    const allOrdered: { task: PipelineTask; stageId: string; stageOff: boolean }[] = []
    for (const stage of props.stages) {
      const stageOff = stage.enabled === false
      for (const task of stage.tasks || []) {
        allOrdered.push({ task, stageId: stage.id, stageOff })
      }
    }
    const allTasks = new Set(allOrdered.map((item) => item.task.id))
    /** 停用阶段里的任务：整段不跑，所以既不发起跳转、也不该当跳转落点 */
    const offTaskIds = new Set(allOrdered.filter((item) => item.stageOff).map((i) => i.task.id))

    for (const { task, stageOff } of allOrdered) {
      if (stageOff) continue
      const targetId = String(task.onErrorTaskId || '')
      if (!targetId || targetId === task.id || !allTasks.has(targetId)) continue
      // 落点在被停用的阶段里：引擎那边它根本不在执行序列里，画出来等于骗人
      if (offTaskIds.has(targetId)) continue
      const live =
        props.statusOf(task.id)?.key === 'running' || props.statusOf(targetId)?.key === 'running'
      edges.push({
        id: 'err:' + task.id + '->' + targetId,
        source: task.id,
        target: targetId,
        sourceHandle: 'err',
        targetHandle: 'in',
        type: 'pipeline',
        animated: live,
        class: live ? 'flow-edge is-live' : 'flow-edge',
        // 和顺序连线同一套描边：蓝实线 2px，没有虚线、没有红色
        style: { stroke: 'var(--flow-edge)', strokeWidth: 2 },
        // 压在主链路上面：错误分支是重点，别被盖住（也保证两条线重合处优先命中它）
        zIndex: 1
      })
    }

    flowNodes.value = nodes
    flowEdges.value = edges
  }

  /** 结构签名：这些字段变了才重建节点（位置变化不重建） */
  const signature = computed(() =>
    props.stages
      .map(
        (stage) =>
          stage.id +
          '~' +
          stage.title +
          '~' +
          (stage.enabled === false ? '0' : '1') +
          '~' +
          props.stageStateOf(stage) +
          '~' +
          (stage.tasks || [])
            .map(
              (task) =>
                task.id +
                '~' +
                (task.title || '') +
                '~' +
                (task.enabled === false ? '0' : '1') +
                '~' +
                (task.linked === false ? 'u' : 'l') +
                '~' +
                (props.statusOf(task.id)?.key || '') +
                '~' +
                (task.continueOnError ? 'c' : '') +
                '~' +
                (task.onErrorTaskId || '') +
                '~' +
                JSON.stringify(task.input || {})
            )
            .join(',')
      )
      .join('|')
  )

  watch(signature, rebuild, { immediate: true })

  /** 异步加载完成后才拿到坐标：只在用户还没动过位置时应用 */
  watch(
    () => props.layout,
    (value) => {
      if (!value || layoutTouched) return
      if (!Object.keys(value.stages || {}).length && !Object.keys(value.tasks || {}).length) return
      positions.stages = { ...(value.stages || {}) }
      positions.tasks = { ...(value.tasks || {}) }
      // 换了一条流水线的坐标：任务序列比对要重置，否则会误判「结构变了」把坐标清掉
      lastStageKeys.clear()
      rebuild()
      nextTick(() => fitAll())
    },
    { deep: true }
  )

  /** 底部终端展开 / 收起会改变画布高度：重新对准视图，否则内容会跑到视野外 */
  watch(
    () => props.bottomOffset,
    () => {
      nextTick(() => fitAll())
    }
  )

  /**
   * 容器尺寸变化（终端展开、窗口缩放）后重新 fit。
   * 用 ResizeObserver 而不是只在 bottomOffset 变化时处理：首次挂载、侧边栏收起
   * 都会改尺寸，漏掉就会出现「内容偏在画布下半部分」。
   */
  const canvasRef = ref<HTMLElement | null>(null)
  let canvasObserver: ResizeObserver | null = null
  let resizeTimer: ReturnType<typeof setTimeout> | null = null

  onMounted(() => {
    const el = canvasRef.value
    if (!el || typeof ResizeObserver === 'undefined') return
    canvasObserver = new ResizeObserver(() => {
      if (resizeTimer) clearTimeout(resizeTimer)
      resizeTimer = setTimeout(() => fitAll(), 120)
    })
    canvasObserver.observe(el)
  })

  onBeforeUnmount(() => {
    canvasObserver?.disconnect()
    if (resizeTimer) clearTimeout(resizeTimer)
  })

  /** 从空画布加上第一个阶段时，把视图对准一次（否则新节点在视口外） */
  watch(
    () => props.stages.length,
    (next, prev) => {
      if (prev === 0 && next > 0) nextTick(() => fitAll())
    }
  )

  const onNodesInitialized = () => {
    // 首次渲染后把视图对准内容，避免节点在视口外
    nextTick(() => fitAll())
  }

  /** 拖动结束：把 Vue Flow 的实时坐标收回本地，并抛给页面保存 */
  const onDragStop = (payload: any) => {
    const nodes: Node[] = payload?.nodes || []
    if (!nodes.length) return
    layoutTouched = true
    for (const node of nodes) {
      if (node.type === 'stage') {
        const id = String(node.id).replace(/^stage:/, '')
        positions.stages[id] = { x: node.position.x, y: node.position.y }
      } else if (node.parentNode) {
        positions.tasks[node.id] = { x: node.position.x, y: node.position.y }
      }
    }
    emit('layout-change', {
      stages: { ...positions.stages },
      tasks: { ...positions.tasks }
    })
  }

  /**
   * 连线有两种语义，靠「从哪个出口拖出来的」区分：
   * · 右侧上点（out，成功后） → 调整执行顺序（把目标接进执行链）
   * · 右侧下点（err，失败后） → 配「失败后跳转」（源失败时跳到目标）
   */
  const onConnect = (connection: Connection) => {
    if (props.readonly) return
    dragConnected = true
    applyConnection(connection.source, connection.target, connection.sourceHandle)
  }

  /**
   * Vue Flow 只在「松手点离某个锚点 connectionRadius 以内」时才发 connect 事件。
   * 卡片有一两百像素宽，用户按提示「把失败后端口拖到卡片上」时往往落在卡片中间，
   * 离左侧 in 锚点很远 → 连线直接作废，看起来像拖不动。
   * 这里补一层兜底：松手时若没触发 connect，就看落点下面是不是某张任务卡片。
   */
  let dragSource: { nodeId: string; handleId: string } | null = null
  let dragConnected = false

  const onConnectStart = (payload: any) => {
    const nodeId = payload?.nodeId ? String(payload.nodeId) : ''
    dragSource = nodeId ? { nodeId, handleId: String(payload?.handleId || '') } : null
    dragConnected = false
  }

  const onConnectEnd = (event: any) => {
    const source = dragSource
    const already = dragConnected
    dragSource = null
    dragConnected = false
    if (props.readonly || already || !source) return

    const x = event?.clientX ?? event?.changedTouches?.[0]?.clientX
    const y = event?.clientY ?? event?.changedTouches?.[0]?.clientY
    if (typeof x !== 'number' || typeof y !== 'number') return

    // 连线拖拽时指针下方可能有 connectionline 图层，逐层找第一个任务卡片
    const stack = document.elementsFromPoint(x, y) || []
    const hit = stack.find((el) => el instanceof Element && el.closest('.vue-flow__node-task'))
    const targetId = hit?.closest('.vue-flow__node-task')?.getAttribute('data-id') || ''
    if (!targetId) return
    applyConnection(source.nodeId, targetId, source.handleId)
  }

  const applyConnection = (
    source: string | null | undefined,
    target: string | null | undefined,
    sourceHandle: string | null | undefined
  ) => {
    if (!source || !target || source === target) return
    if (String(source).indexOf('stage:') === 0) return
    if (String(target).indexOf('stage:') === 0) return
    const kind = sourceHandle === 'err' ? 'error' : 'reorder'
    emit('connect-task', {
      sourceTaskId: String(source),
      targetTaskId: String(target),
      kind
    })
    // 拼接会改阶段内任务数量（容器高度随之变化），把视图重新对准一次
    setTimeout(fitAll, 160)
  }

  const onNodeDblClick = ({ node }: any) => {
    if (node?.type !== 'task') return
    const [stageIndex, taskIndex] = findTask(node.id)
    if (stageIndex < 0) return
    emit('open-task', stageIndex, taskIndex)
  }

  /**
   * 点连线 = 删这条线。
   * 顺序连线删掉 → 目标任务变「未连线」，不再执行；
   * 「失败后」连线删掉 → 清掉源任务的 onErrorTaskId。
   * 具体怎么改数据由页面决定（这里只把语义抛上去），确认弹窗也在页面里。
   */
  const onEdgeClick = ({ edge }: any) => {
    if (props.readonly || !edge) return
    const id = String(edge.id || '')
    const isError = id.startsWith('err:')
    emit('edge-delete', {
      sourceTaskId: String(edge.source || ''),
      targetTaskId: String(edge.target || ''),
      kind: isError ? 'error' : 'next'
    })
  }

  const findTask = (taskId: string): [number, number] => {
    for (let si = 0; si < props.stages.length; si++) {
      const ti = (props.stages[si].tasks || []).findIndex((task) => task.id === taskId)
      if (ti >= 0) return [si, ti]
    }
    return [-1, -1]
  }

  /** 自动整理：丢掉手工坐标，按阶段重新排一遍 */
  const reflow = () => {
    layoutTouched = true
    positions.stages = {}
    positions.tasks = {}
    rebuild()
    nextTick(() => fitAll())
    emit('layout-change', { stages: {}, tasks: {} })
  }

  /**
   * 对准视图。
   * 不用 fitView：它会读 Vue Flow 缓存的容器尺寸，容器高度刚变（终端展开 / 收起）时
   * 拿到的是旧值，结果内容偏在画布下半部分。这里按节点几何自己算，结果确定。
   */
  const fitAll = () => {
    const el = canvasRef.value
    if (!el || !props.stages.length) return
    const width = el.clientWidth
    const height = el.clientHeight
    if (!width || !height) return

    const rects = props.stages.map((stage, index) => {
      const pos = positions.stages[stage.id] || autoStagePos(index)
      return { x: pos.x, y: pos.y, w: STAGE_W, h: stageHeight(stage.tasks?.length || 0) }
    })
    const minX = Math.min(...rects.map((r) => r.x))
    const minY = Math.min(...rects.map((r) => r.y))
    const maxX = Math.max(...rects.map((r) => r.x + r.w))
    const maxY = Math.max(...rects.map((r) => r.y + r.h))
    const boxW = Math.max(1, maxX - minX)
    const boxH = Math.max(1, maxY - minY)

    const pad = 48
    const zoom = Math.min(1, (width - pad * 2) / boxW, (height - pad * 2) / boxH)
    setViewport(
      {
        x: (width - boxW * zoom) / 2 - minX * zoom,
        y: (height - boxH * zoom) / 2 - minY * zoom,
        zoom
      },
      { duration: 200 }
    )
  }

  /** 小地图按环节上色，和卡片左边框一致 */
  /** 小地图按环节上色，和卡片左边框一致；停用阶段里的任务压成灰色，和画布上的降饱和对齐 */
  const miniMapColor = (node: Node) => {
    if (node.type === 'stage') return 'transparent'
    if ((node.data as any)?.stageOff) return '#bdc1c6'
    const kind = (node.data as any)?.kindKey
    if (kind === 'cert') return '#1a73e8'
    if (kind === 'notify') return '#e37400'
    return '#1e8e3e'
  }

  defineExpose({ reflow, fitAll, getViewport })
</script>

<style scoped>
  /* ---------------- 画布外壳 ---------------- */
  .pipeline-canvas {
    position: relative;
    height: clamp(520px, calc(100vh - 286px), 940px);
    overflow: hidden;
    background: var(--g-surface);
    border: 1px solid var(--g-line);
    border-radius: 16px;

    /* 连线颜色：Google blue 500，浅底上也看得清；hover / 运行中变深 */
    --flow-edge: #4285f4;
    --flow-edge-live: var(--g-blue);
  }

  .pipeline-canvas :deep(.vue-flow) {
    background: var(--g-surface);
  }

  /* 点阵背景在暗色下要压暗，否则一片白点 */
  .pipeline-canvas :deep(.vue-flow__background pattern circle) {
    fill: var(--g-line);
  }

  /* ---------------- 通用节点 ---------------- */
  .flow-node {
    font-family: var(--g-font);
  }

  /* ⚠️ 必读：Vue Flow 的 NodeWrapper 会给节点容器写「内联」pointer-events。
     判定条件是 hasPointerEvents = isSelectable || isDraggable || 有 nodeClick 等钩子。
     第 2 轮把节点改成「位置固定」（draggable: false、selectable: false）时，
     它直接判定这个节点不需要指针事件，内联写死 pointer-events: none ——
     节点里所有按钮、卡片双击、连线锚点全部点不到（「画布模式加不了任务」的真凶）。
     现在阶段外框可以拖了（draggable: true），它又会反过来内联写 all，
     于是整块阶段矩形（含留白）都吃掉指针、画布没法平移。
     所以这里用 !important 把容器压回穿透：需要交互的部分逐个打开。
     拖动依然有效 —— 指针落在子元素（标题条 / 卡片）上，事件照常冒泡到节点容器，
     Vue Flow 的 pointerdown 监听挂在容器上，照样能起拖。 */
  .pipeline-canvas :deep(.vue-flow__node) {
    pointer-events: none !important;
  }

  .pipeline-canvas :deep(.vue-flow__node .stage-node-head),
  .pipeline-canvas :deep(.vue-flow__node .stage-node-actions),
  .pipeline-canvas :deep(.vue-flow__node .stage-node-switch),
  .pipeline-canvas :deep(.vue-flow__node .stage-node-add),
  .pipeline-canvas :deep(.vue-flow__node .stage-node-limit),
  .pipeline-canvas :deep(.vue-flow__node .task-node) {
    pointer-events: auto;
  }

  /* 锚点：只放开门/出口这两个真锚点，程序连线用的 is-ghost 必须继续穿透。
     :not(.is-ghost) 顺带把特异性抬高一级，压过下面 is-ghost 的 none。 */
  .pipeline-canvas :deep(.vue-flow__node .flow-handle:not(.is-ghost)) {
    pointer-events: auto;
  }

  /* ---------------- 阶段容器 ---------------- */
  .stage-node {
    position: relative;
    padding: 0;
    background: color-mix(in srgb, var(--stage-color) 4%, var(--g-surface));
    border: 1.5px dashed color-mix(in srgb, var(--stage-color) 34%, transparent);
    border-radius: 18px;
    transition:
      border-color 0.16s ease,
      background 0.16s ease;
  }

  .stage-node:hover {
    border-color: color-mix(in srgb, var(--stage-color) 60%, transparent);
  }

  .stage-node.is-success {
    border-style: solid;
    border-color: color-mix(in srgb, var(--g-green) 40%, transparent);
  }

  .stage-node.is-failed {
    border-style: solid;
    border-color: color-mix(in srgb, var(--g-red) 44%, transparent);
  }

  .stage-node.is-running {
    border-style: solid;
    border-color: color-mix(in srgb, var(--g-amber) 55%, transparent);
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--g-amber) 10%, transparent);
  }

  .stage-node-head {
    position: relative;
    display: flex;
    gap: 8px;
    align-items: center;
    height: 44px;
    padding: 0 8px 0 12px;
    /* 阶段外框可以拖：标题条是抓取区（和窗口标题栏一样），
       卡片本体（任务卡）拖也是整体移动，阶段留白仍然用来平移画布 */
    cursor: grab;
  }

  .stage-node-head:active {
    cursor: grabbing;
  }

  /*
   * 阶段序号：实心圆 + 一圈「白边」+ 柔和投影（参考图的硬币质感）。
   * 白边取 --g-surface 而不是写死 #fff：暗色模式下它就是深色卡片底，
   * 不会变成一圈刺眼的白环。投影掺一点阶段色，让圆从浅底上「浮」起来。
   * box-sizing 显式写死：白边算在 26px 里面，不然徽标会撑到 32px、把标题挤走。
   */
  .stage-node-index {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    box-sizing: border-box;
    width: 26px;
    height: 26px;
    font-size: 11.5px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    color: #fff;
    background: var(--stage-color);
    border: 3px solid var(--g-surface);
    border-radius: 50%;
    box-shadow:
      0 1px 2px rgba(60, 64, 67, 0.16),
      0 3px 7px color-mix(in srgb, var(--stage-color) 32%, transparent);
  }

  /* 暗色下 --g-blue 是浅蓝（#8ab4f8），白字读不清，反过来用深色字 */
  .dark .stage-node-index {
    color: #202124;
    box-shadow:
      0 1px 2px rgba(0, 0, 0, 0.5),
      0 3px 8px color-mix(in srgb, var(--stage-color) 26%, transparent);
  }

  /*
   * 阶段启停开关（头部最右侧，常驻可见）。
   * 不用 ElSwitch：这里是画布节点内部，尺寸/主题都要跟着节点缩放走，
   * 一个 30×18 的原生 button 更可控，也不会被 Vue Flow 的拖拽吃掉点击。
   */
  .stage-node-switch {
    position: relative;
    flex: 0 0 auto;
    width: 30px;
    height: 18px;
    padding: 0;
    cursor: pointer;
    background: var(--g-line);
    border: 0;
    border-radius: 100px;
    transition: background 0.16s ease;
  }

  .stage-node-switch .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    /* 写死白色而不是 --g-surface：暗色模式下 --g-surface 是深灰，
       关态（深灰轨道 + 深灰滑块）几乎看不出滑块在哪 */
    background: #fff;
    border-radius: 50%;
    box-shadow: 0 1px 2px rgba(60, 64, 67, 0.35);
    transition: transform 0.16s ease;
  }

  .stage-node-switch.is-on {
    background: var(--stage-color);
  }

  .stage-node-switch.is-on .knob {
    transform: translateX(12px);
  }

  .stage-node-switch:hover {
    filter: brightness(0.94);
  }

  .stage-node-switch:focus-visible {
    outline: 2px solid var(--g-blue);
    outline-offset: 2px;
  }

  /* 停用状态：整段灰掉，一眼能看出「这一段不会跑」 */
  .stage-node.is-off {
    background: var(--g-fill);
    border-color: var(--g-line);
  }

  .stage-node.is-off .stage-node-title {
    color: var(--g-text-3);
  }

  .stage-node.is-off .stage-node-kind {
    color: var(--g-text-3);
    background: var(--g-fill-hover);
  }

  .stage-node.is-off .stage-node-index {
    background: var(--g-text-3);
    box-shadow: 0 1px 2px rgba(60, 64, 67, 0.14);
  }

  .stage-node.is-off .stage-node-add {
    color: var(--g-text-3);
    background: transparent;
    border-color: var(--g-line);
  }

  .stage-node-title {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    font-size: 13px;
    font-weight: 600;
    color: var(--g-text);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .stage-node-kind {
    flex: 0 0 auto;
    padding: 1px 7px;
    font-size: 11px;
    color: var(--stage-color);
    white-space: nowrap;
    background: color-mix(in srgb, var(--stage-color) 12%, transparent);
    border-radius: 100px;
    transition: opacity 0.14s ease;
  }

  .stage-node-spacer {
    flex: 1 1 auto;
  }

  /* 操作按钮做成浮层：平时不占头部布局，否则阶段名会被挤成「申…」。
     right 让开最右侧常驻的启停开关（30px + 间距），否则浮层会盖住它。 */
  .stage-node-actions {
    position: absolute;
    top: 50%;
    right: 42px;
    display: flex;
    gap: 2px;
    align-items: center;
    padding: 2px 4px;
    background: var(--g-surface);
    border: 1px solid var(--g-line-2);
    border-radius: 100px;
    box-shadow: 0 2px 8px rgba(60, 64, 67, 0.14);
    opacity: 0;
    transform: translateY(-50%);
    transition: opacity 0.16s ease;
  }

  .stage-node:hover .stage-node-actions {
    opacity: 1;
  }

  .stage-node:hover .stage-node-kind {
    opacity: 0;
  }

  .stage-node-actions button,
  .task-node-actions button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    font-size: 13px;
    color: var(--g-text-2);
    cursor: pointer;
    background: transparent;
    border: 0;
    border-radius: 50%;
    transition:
      color 0.14s ease,
      background 0.14s ease;
  }

  .stage-node-actions button:hover,
  .task-node-actions button:hover {
    color: var(--g-text);
    background: color-mix(in srgb, var(--g-text) 8%, transparent);
  }

  .stage-node-actions button.is-danger:hover,
  .task-node-actions button.is-danger:hover {
    color: var(--g-red);
    background: var(--g-red-50);
  }

  .stage-node-actions button:disabled {
    cursor: not-allowed;
    opacity: 0.35;
  }

  /* 阶段底部常驻的「添加任务」按钮：虚线框 + 环节色，一眼看出这里是入口 */
  .stage-node-add {
    position: absolute;
    right: 16px;
    bottom: 16px;
    left: 16px;
    display: flex;
    gap: 6px;
    align-items: center;
    justify-content: center;
    height: 34px;
    font-family: var(--g-font);
    font-size: 12px;
    color: var(--stage-color);
    cursor: pointer;
    background: color-mix(in srgb, var(--stage-color) 5%, transparent);
    border: 1px dashed color-mix(in srgb, var(--stage-color) 42%, transparent);
    border-radius: 10px;
    transition:
      background 0.14s ease,
      border-color 0.14s ease;
  }

  .stage-node-add:hover {
    background: color-mix(in srgb, var(--stage-color) 12%, transparent);
    border-color: var(--stage-color);
  }

  /* 计数做成浅色小字，不抢按钮主文案 */
  .stage-node-add em {
    font-size: 11px;
    font-style: normal;
    color: color-mix(in srgb, var(--stage-color) 60%, transparent);
  }

  /* 满 5 个任务：按钮换成不可点的提示条，别再让人以为还能加 */
  .stage-node-limit {
    position: absolute;
    right: 16px;
    bottom: 16px;
    left: 16px;
    display: flex;
    gap: 6px;
    align-items: center;
    justify-content: center;
    height: 34px;
    font-size: 12px;
    color: var(--g-text-3);
    cursor: not-allowed;
    background: var(--g-fill);
    border: 1px dashed var(--g-line);
    border-radius: 10px;
  }

  /* ---------------- 任务卡片 ---------------- */
  .task-node {
    position: relative;
    display: flex;
    flex-direction: column;
    /* 宽高由节点 data 内联给出（canvas-types.ts 的 CANVAS_METRICS），这里不写死，避免两处漂移 */
    padding: 12px 13px 9px;
    background: var(--g-surface);
    border: 1px solid var(--g-line);
    border-radius: 14px;
    box-shadow: 0 1px 2px rgba(60, 64, 67, 0.1);
    transition:
      box-shadow 0.16s ease,
      border-color 0.16s ease,
      transform 0.16s ease;
  }

  /*
   * 注意：这里绝对不能写 overflow: hidden。
   * 连线锚点挂在卡片左右边缘、中心点正好落在边框上，一旦裁切，
   * pointerdown 会打到卡片本体上，Vue Flow 收不到 handle 事件，
   * 表现就是「拖不出连线」。
   */

  .task-node:hover {
    border-color: color-mix(in srgb, var(--node-color) 45%, var(--g-line));
    box-shadow: 0 6px 16px rgba(60, 64, 67, 0.14);
  }

  .task-node.is-selected {
    border-color: var(--node-color);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--node-color) 18%, transparent);
  }

  .task-node.is-disabled {
    background: var(--g-fill);
  }

  .task-node.is-disabled .task-node-head,
  .task-node.is-disabled .task-node-desc,
  .task-node.is-disabled .task-node-meta {
    opacity: 0.55;
  }

  /*
   * 阶段整段停用：里面的卡片一起降饱和 + 虚线边。
   * 任务自己的 enabled 还是 true，但整段不执行 —— 不这样处理的话，
   * 灰掉的阶段里躺着一张「看起来正常」的卡片，用户会以为它还会跑。
   */
  .task-node.is-stage-off {
    background: var(--g-fill);
    border-style: dashed;
  }

  .task-node.is-stage-off .task-node-head,
  .task-node.is-stage-off .task-node-desc,
  .task-node.is-stage-off .task-node-meta,
  .task-node.is-stage-off .task-node-foot {
    opacity: 0.45;
  }

  /* 上次执行结果的描边：成功绿 / 失败红 / 运行中琥珀 */
  .task-node.is-success {
    border-color: color-mix(in srgb, var(--g-green) 45%, var(--g-line));
  }

  .task-node.is-failed {
    border-color: color-mix(in srgb, var(--g-red) 50%, var(--g-line));
  }

  .task-node.is-running {
    border-color: var(--g-amber);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--g-amber) 16%, transparent);
  }

  .task-node-head {
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }

  .task-node-icon {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
  }

  .task-node-title-wrap {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }

  .task-node-title {
    overflow: hidden;
    font-size: 13px;
    font-weight: 600;
    line-height: 18px;
    color: var(--g-text);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .task-node-sub {
    overflow: hidden;
    font-size: 11px;
    line-height: 14px;
    color: var(--g-text-3);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .task-node-state {
    display: inline-flex;
    flex: 0 0 auto;
    gap: 4px;
    align-items: center;
    height: 18px;
    padding: 0 7px;
    font-size: 11px;
    color: var(--g-text-2);
    white-space: nowrap;
    background: var(--g-fill-hover);
    border-radius: 100px;
  }

  .task-node-state .dot {
    width: 5px;
    height: 5px;
    background: currentcolor;
    border-radius: 50%;
  }

  .task-node-state.is-success {
    color: var(--g-green);
    background: var(--g-green-50);
  }

  .task-node-state.is-failed {
    color: var(--g-red);
    background: var(--g-red-50);
  }

  .task-node-state.is-running {
    color: var(--g-amber);
    background: var(--g-amber-50);
  }

  .task-node-state.is-running .dot {
    animation: node-pulse 1.1s ease-in-out infinite;
  }

  .task-node-state.is-skipped,
  .task-node-state.is-off {
    color: var(--g-text-3);
  }

  /* 未连线：用红色系而不是灰色 —— 它是「不会执行」，比停用更需要被看见 */
  .task-node-state.is-unlinked {
    color: var(--g-red);
  }

  .task-node-state.is-unlinked .dot {
    background: var(--g-red);
  }

  @keyframes node-pulse {
    0%,
    100% {
      opacity: 1;
      transform: scale(1);
    }

    50% {
      opacity: 0.35;
      transform: scale(0.7);
    }
  }

  .task-node-desc {
    display: -webkit-box;
    margin: 9px 0 0;
    overflow: hidden;
    font-size: 12px;
    line-height: 17px;
    color: var(--g-text-2);
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .task-node-meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin: 7px 0 0;
  }

  .task-node-meta-row {
    display: flex;
    gap: 6px;
    align-items: baseline;
    min-width: 0;
    font-size: 11px;
    line-height: 15px;
  }

  .task-node-meta-row dt {
    flex: 0 0 auto;
    color: var(--g-text-3);
  }

  .task-node-meta-row dd {
    flex: 1 1 auto;
    min-width: 0;
    margin: 0;
    overflow: hidden;
    color: var(--g-text-2);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .task-node-foot {
    display: flex;
    gap: 6px;
    align-items: center;
    height: 20px;
    margin-top: auto;
    padding-top: 6px;
    border-top: 1px solid var(--g-line-2);
  }

  .task-node-seq {
    font-size: 10px;
    font-variant-numeric: tabular-nums;
    color: var(--g-text-3);
  }

  .task-node-foot-text {
    flex: 1 1 auto;
    overflow: hidden;
    font-size: 10px;
    color: var(--g-text-3);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .task-node-actions {
    display: flex;
    gap: 1px;
    opacity: 0;
    transition: opacity 0.16s ease;
  }

  .task-node:hover .task-node-actions {
    opacity: 1;
  }

  .task-node-actions button {
    width: 20px;
    height: 20px;
    font-size: 12px;
  }

  /* ---------------- 连线与锚点 ---------------- */
  /*
   * 连线层压在阶段容器上方：阶段容器的底色不透明，压在下面会把线整段盖住，
   * 跨阶段的「失败后」直线就只剩阶段之间两小段、看着像断线。
   * 任务卡片仍在连线上面（z-index: 3），所以卡片内容、端口和「成功后/失败后」
   * 标签不会被线挡住；失败线从中间卡片背后穿过是预期效果。
   */
  .pipeline-canvas :deep(.vue-flow__edges) {
    z-index: 2 !important;
  }

  .pipeline-canvas :deep(.vue-flow__node-task) {
    z-index: 3 !important;
  }

  .pipeline-canvas :deep(.vue-flow__edge-path) {
    stroke: var(--flow-edge);
    stroke-width: 2;
    transition: stroke 0.16s ease;
  }

  /* 点连线就删掉它：鼠标移上去要能看出「这条线是可以点的」 */
  .pipeline-canvas :deep(.vue-flow__edge) {
    cursor: pointer;
  }

  .pipeline-canvas :deep(.vue-flow__edge:hover .vue-flow__edge-path) {
    stroke: var(--g-blue);
    stroke-width: 3;
  }

  .pipeline-canvas :deep(.vue-flow__edge.animated .vue-flow__edge-path) {
    stroke: var(--flow-edge-live);
    stroke-dasharray: 6 4;
  }

  /* 锚点：平时是小白点，hover 放大变实心蓝。
     放大只能用独立的 scale 属性 —— 覆盖 transform 会把 Vue Flow 的
     translate(-50%, -50%) 定位一起干掉，锚点被推出卡片，pointerdown 就命中不到它了。 */
  .pipeline-canvas :deep(.flow-handle) {
    z-index: 3;
    width: 10px;
    height: 10px;
    background: var(--g-surface);
    border: 2px solid var(--flow-edge);
    opacity: 0;
    transition:
      opacity 0.16s ease,
      scale 0.16s ease,
      background 0.16s ease;
  }

  .pipeline-canvas :deep(.task-node:hover .flow-handle),
  .pipeline-canvas :deep(.vue-flow__node.selected .flow-handle) {
    opacity: 1;
  }

  .pipeline-canvas :deep(.flow-handle:hover) {
    background: var(--g-blue);
    border-color: var(--g-blue);
    scale: 1.3;
  }

  /* 进口 / 成功出口常驻低透明度：一眼看出「一个进口、两个出口」；
     hover 卡片时三个端口一起实心，方便拖动。失败出口在下面单独画成红色。 */
  .pipeline-canvas :deep(.flow-handle.is-in),
  .pipeline-canvas :deep(.flow-handle.is-out) {
    opacity: 0.4;
  }

  /* 两个出口的常驻文字标签：放在卡片右侧留白（stagePadRight）里，
     和端口同一高度、往上抬 4px，不压卡片内容，也不压从端口出来的连线。 */
  .flow-port-label {
    position: absolute;
    left: calc(100% + 6px);
    z-index: 2;
    height: 16px;
    padding: 0 5px;
    font-family: var(--g-font);
    font-size: 10px;
    font-weight: 600;
    line-height: 14px;
    white-space: nowrap;
    pointer-events: none;
    border: 1px solid transparent;
    border-radius: 5px;
    transform: translateY(-100%);
  }

  .flow-port-label.is-out {
    top: calc(50% - 4px);
    /* 比连线深一点：10px 小字纯 #4285f4 对比度偏低，混一点正文色保证看得清 */
    color: color-mix(in srgb, var(--flow-edge) 72%, var(--g-text));
    background: color-mix(in srgb, var(--flow-edge) 8%, var(--g-surface));
    border-color: color-mix(in srgb, var(--flow-edge) 30%, transparent);
  }

  .flow-port-label.is-err {
    top: calc(74% - 4px);
    color: color-mix(in srgb, var(--g-red) 85%, var(--g-text));
    background: color-mix(in srgb, var(--g-red) 7%, var(--g-surface));
    border-color: color-mix(in srgb, var(--g-red) 28%, transparent);
  }

  .flow-port-label.is-err.is-on {
    color: var(--g-red);
    background: var(--g-red-50);
    border-color: color-mix(in srgb, var(--g-red) 50%, transparent);
  }

  /* 失败后跳转的出口：常驻半透明红点，悬停才完全显现。
     配过跳转的（is-on）直接实心红点，一眼能看出这条链上有兜底。 */
  .pipeline-canvas :deep(.flow-handle.is-err) {
    top: 74%;
    background: var(--g-surface);
    border-color: color-mix(in srgb, var(--g-red) 65%, transparent);
    opacity: 0.45;
  }

  .pipeline-canvas :deep(.task-node:hover .flow-handle.is-err) {
    opacity: 1;
  }

  .pipeline-canvas :deep(.flow-handle.is-err:hover) {
    background: var(--g-red);
    border-color: var(--g-red);
    scale: 1.35;
  }

  .pipeline-canvas :deep(.flow-handle.is-err.is-on) {
    background: var(--g-red);
    border-color: var(--g-red);
    opacity: 1;
  }

  /* 程序连线专用的隐藏锚点：不显示、不接收指针。
     hover 规则的选择器更长，这里必须 !important 才能压住。 */
  .pipeline-canvas :deep(.flow-handle.is-ghost) {
    width: 1px;
    height: 1px;
    pointer-events: none !important;
    opacity: 0 !important;
    border: 0;
  }

  /* ---------------- 空画布 ---------------- */
  .canvas-empty {
    position: absolute;
    top: 50%;
    left: 50%;
    z-index: 5;
    width: min(360px, 80%);
    text-align: center;
    pointer-events: none;
    transform: translate(-50%, -50%);
  }

  .canvas-empty-icon {
    font-size: 34px;
    color: var(--g-line);
  }

  .canvas-empty-title {
    margin: 8px 0 4px;
    font-size: 14px;
    font-weight: 600;
    color: var(--g-text-2);
  }

  .canvas-empty-desc {
    margin: 0;
    font-size: 12px;
    line-height: 18px;
    color: var(--g-text-3);
  }

  /* ---------------- 画布工具条 ---------------- */
  .canvas-toolbar {
    position: absolute;
    top: 12px;
    right: 12px;
    left: 12px;
    z-index: 6;
    display: flex;
    gap: 12px;
    align-items: center;
    justify-content: space-between;
    pointer-events: none;
  }

  .canvas-toolbar-hint {
    display: inline-flex;
    gap: 6px;
    align-items: center;
    max-width: 62%;
    padding: 6px 12px;
    overflow: hidden;
    font-size: 12px;
    color: var(--g-text-2);
    text-overflow: ellipsis;
    white-space: nowrap;
    pointer-events: auto;
    background: color-mix(in srgb, var(--g-surface) 88%, transparent);
    border: 1px solid var(--g-line-2);
    border-radius: 100px;
    backdrop-filter: blur(6px);
  }

  .canvas-toolbar-actions {
    display: flex;
    gap: 6px;
    pointer-events: auto;
  }

  .canvas-toolbar-actions button {
    display: inline-flex;
    gap: 5px;
    align-items: center;
    height: 30px;
    padding: 0 12px;
    font-size: 12px;
    color: var(--g-text-2);
    cursor: pointer;
    background: var(--g-surface);
    border: 1px solid var(--g-line);
    border-radius: 100px;
    transition:
      color 0.14s ease,
      border-color 0.14s ease,
      background 0.14s ease;
  }

  .canvas-toolbar-actions button:hover {
    color: var(--g-blue);
    background: var(--g-blue-50);
    border-color: color-mix(in srgb, var(--g-blue) 40%, transparent);
  }

  /* ---------------- Vue Flow 自带控件适配 ---------------- */
  .pipeline-canvas :deep(.vue-flow__controls) {
    gap: 4px;
    padding: 4px;
    background: var(--g-surface);
    border: 1px solid var(--g-line);
    border-radius: 12px;
    box-shadow: 0 2px 6px rgba(60, 64, 67, 0.12);
  }

  .pipeline-canvas :deep(.vue-flow__controls-button) {
    width: 26px;
    height: 26px;
    color: var(--g-text-2);
    background: transparent;
    border: 0;
    border-radius: 8px;
  }

  .pipeline-canvas :deep(.vue-flow__controls-button:hover) {
    color: var(--g-text);
    background: var(--g-fill-hover);
  }

  .pipeline-canvas :deep(.vue-flow__controls-button svg) {
    fill: currentcolor;
  }

  .pipeline-canvas :deep(.vue-flow__minimap) {
    overflow: hidden;
    background: var(--g-fill);
    border: 1px solid var(--g-line);
    border-radius: 12px;
  }

  .pipeline-canvas :deep(.vue-flow__minimap-mask) {
    fill: color-mix(in srgb, var(--g-text) 8%, transparent);
  }

  /* 连线时的临时虚线 */
  .pipeline-canvas :deep(.vue-flow__connection-path) {
    stroke: var(--g-blue);
    stroke-width: 2;
    stroke-dasharray: 5 4;
  }

  /* 窄屏：工具条提示收起，画布矮一点 */
  @media only screen and (width <= 900px) {
    .pipeline-canvas {
      height: clamp(460px, calc(100vh - 320px), 720px);
    }

    .canvas-toolbar-hint {
      display: none;
    }

    .canvas-toolbar {
      justify-content: flex-end;
    }

    .canvas-toolbar-actions button span {
      display: none;
    }

    .canvas-toolbar-actions button {
      padding: 0 9px;
    }
  }
</style>
