<!-- 水平菜单 -->
<template>
  <nav class="horizontal-menu-shell overflow-hidden" aria-label="主导航">
    <ElMenu
      :ellipsis="false"
      mode="horizontal"
      :default-active="routerPath"
      :text-color="isDark ? 'var(--art-gray-800)' : 'var(--art-gray-700)'"
      :popper-offset="-6"
      background-color="transparent"
      :show-timeout="50"
      :hide-timeout="50"
      popper-class="horizontal-menu-popper"
      class="horizontal-menu w-full justify-center border-none"
    >
      <HorizontalSubmenu
        v-for="item in filteredMenuItems"
        :key="item.path"
        :item="item"
        :isMobile="false"
        :level="0"
      />
    </ElMenu>
  </nav>
</template>

<script setup lang="ts">
  import type { AppRouteRecord } from '@/types/router'
  import HorizontalSubmenu from './widget/HorizontalSubmenu.vue'
  import { useSettingStore } from '@/store/modules/setting'

  defineOptions({ name: 'ArtHorizontalMenu' })

  const settingStore = useSettingStore()
  const { isDark } = storeToRefs(settingStore)

  interface Props {
    /** 菜单列表数据 */
    list: AppRouteRecord[]
  }

  const route = useRoute()

  const props = withDefaults(defineProps<Props>(), {
    list: () => []
  })

  /**
   * 过滤后的菜单项列表
   * 只显示未隐藏的菜单项
   */
  const filteredMenuItems = computed(() => {
    return filterMenuItems(props.list)
  })

  /**
   * 当前激活的路由路径
   * 用于菜单高亮显示
   */
  const routerPath = computed(() => String(route.meta.activePath || route.path))

  /**
   * 递归过滤菜单项，移除隐藏的菜单
   * 如果一个父菜单的所有子菜单都被隐藏，则父菜单也会被隐藏
   * @param items 菜单项数组
   * @returns 过滤后的菜单项数组
   */
  const filterMenuItems = (items: AppRouteRecord[]): AppRouteRecord[] => {
    return items
      .filter((item) => {
        // 如果当前项被隐藏，直接过滤掉
        if (item.meta.isHide) {
          return false
        }

        // 如果有子菜单，递归过滤子菜单
        if (item.children && item.children.length > 0) {
          const filteredChildren = filterMenuItems(item.children)
          // 如果所有子菜单都被过滤掉了，则隐藏父菜单
          return filteredChildren.length > 0
        }

        // 叶子节点且未被隐藏，保留
        return true
      })
      .map((item) => ({
        ...item,
        children: item.children ? filterMenuItems(item.children) : undefined
      }))
  }
</script>

<style lang="scss" scoped>
  .horizontal-menu-shell {
    box-sizing: border-box;
    height: var(--art-header-menu-height);
    padding: var(--art-header-menu-shell-padding);
    background: var(--default-box-color);
    border: 1px solid var(--art-card-border);
    border-radius: calc(var(--custom-radius) + 10px);
    box-shadow: var(--art-header-surface-shadow);
  }

  :deep(.horizontal-menu) {
    --el-menu-horizontal-height: var(--art-header-menu-item-height);

    gap: var(--art-header-menu-item-gap);
    height: var(--art-header-menu-item-height);
    border-bottom: none !important;
  }

  :deep(.el-menu--horizontal > .el-menu-item),
  :deep(.el-menu--horizontal > .el-sub-menu > .el-sub-menu__title) {
    height: var(--art-header-menu-item-height);
    padding: 0 var(--art-header-menu-item-padding) !important;
    line-height: var(--art-header-menu-item-height);
    color: var(--art-gray-700);
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: calc(var(--custom-radius) + 6px);
    transition:
      color 0.2s ease,
      background-color 0.2s ease,
      border-color 0.2s ease;
  }

  :deep(.el-menu--horizontal > .el-menu-item:hover),
  :deep(.el-menu--horizontal > .el-sub-menu:hover > .el-sub-menu__title) {
    color: var(--theme-color) !important;
    background: var(--art-hover-color) !important;
  }

  :deep(.el-menu--horizontal > .el-menu-item.is-active),
  :deep(.el-menu--horizontal > .el-sub-menu.is-active > .el-sub-menu__title) {
    color: var(--theme-color) !important;
    background: color-mix(in srgb, var(--theme-color) 8%, var(--default-box-color)) !important;
    border-color: color-mix(in srgb, var(--theme-color) 55%, var(--default-border)) !important;
  }

  :deep(.el-menu--horizontal > .el-menu-item.is-active .art-svg-icon),
  :deep(.el-menu--horizontal > .el-sub-menu.is-active > .el-sub-menu__title .art-svg-icon) {
    color: var(--theme-color) !important;
  }

  :deep(.el-menu--horizontal > .el-menu-item:focus-visible),
  :deep(.el-menu--horizontal > .el-sub-menu > .el-sub-menu__title:focus-visible) {
    outline: 2px solid color-mix(in srgb, var(--theme-color) 55%, transparent);
    outline-offset: -2px;
  }

  :deep(.el-menu--horizontal > .el-sub-menu > .el-sub-menu__title) {
    padding-right: var(--art-header-menu-submenu-padding) !important;
  }

  :deep(.el-menu--horizontal > .el-sub-menu > .el-sub-menu__title .el-sub-menu__icon-arrow) {
    right: var(--art-header-menu-arrow-offset);
  }

  @media (width <= 768px) {
    .horizontal-menu-shell {
      height: var(--art-header-menu-compact-height);
    }

    :deep(.el-menu--horizontal > .el-menu-item),
    :deep(.el-menu--horizontal > .el-sub-menu > .el-sub-menu__title) {
      padding-right: var(--art-header-menu-item-compact-padding) !important;
      padding-left: var(--art-header-menu-item-compact-padding) !important;
    }
  }
</style>
